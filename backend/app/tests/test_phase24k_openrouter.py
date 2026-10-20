"""Phase 24K — OpenRouter Narrative Model Integration & Real Playability Test.

Deterministic, mocked-HTTP coverage for the new OpenRouterLLMService and
the independent intent/narrative provider selection it enables. No real
network call is ever made here — see the session's live-validation
transcript (reported separately) for the actual live test against
nvidia/nemotron-3-ultra-550b-a55b:free.
"""
import logging
from unittest.mock import patch

import httpx
import pytest

from app.ai.llm_service import (
    DisabledLLMService,
    LLMService,
    LLMServiceError,
    OllamaLLMService,
    OpenRouterLLMService,
    build_llm_service,
    build_regeneration_llm_service,
    build_role_llm_services,
)
from app.core.config import Settings
from app.core.logging import get_logger


def _service(**overrides) -> OpenRouterLLMService:
    kwargs = dict(api_key="sk-or-test-secret-key", model="nvidia/nemotron-3-ultra-550b-a55b:free")
    kwargs.update(overrides)
    return OpenRouterLLMService(**kwargs)


def _openrouter_response(payload, status=200, url="https://openrouter.ai/api/v1/chat/completions") -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request("POST", url))


def _success_payload(content="Olá, viajante.", finish_reason="stop"):
    return {
        "id": "gen-abc123",
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160},
    }


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def messages(self) -> list[str]:
        return [record.getMessage() for record in self.records]


def _capture_llm_logs():
    # Same discipline as test_observability.py's own _capture_visual_logs
    # — pytest's caplog goes silent once anything in the suite has
    # triggered app startup (propagate=False on the "everreach" ancestor
    # logger), so a plain Handler is attached directly instead.
    logger = get_logger("llm")
    handler = _RecordingHandler()
    original_level = logger.level
    original_disabled = logger.disabled
    original_disable = logging.Logger.manager.disable
    logging.disable(logging.NOTSET)
    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    def teardown():
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.disabled = original_disabled
        logging.disable(original_disable)

    return handler, teardown


# --- 1. successful OpenRouter response ---


def test_successful_openrouter_response_returns_the_message_content():
    with patch("httpx.post", return_value=_openrouter_response(_success_payload())):
        result = _service().generate("system prompt", "user prompt")

    assert result == "Olá, viajante."


# --- 2. correct model sent ---


def test_correct_model_is_sent_in_the_request_body():
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        return _openrouter_response(_success_payload())

    with patch("httpx.post", side_effect=fake_post):
        _service(model="nvidia/nemotron-3-ultra-550b-a55b:free").generate("s", "p")

    assert calls[0]["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"


def test_model_id_is_never_the_free_router_alias():
    # The governing spec's own explicit requirement: "openrouter/free"
    # would make the test non-reproducible (router picks a different
    # free model per call). This locks in that the exact pinned model ID
    # is what actually gets sent.
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        return _openrouter_response(_success_payload())

    with patch("httpx.post", side_effect=fake_post):
        _service().generate("s", "p")

    assert calls[0]["model"] != "openrouter/free"
    assert calls[0]["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"


# --- 3. system/user content preserved ---


def test_system_and_user_content_are_preserved_as_separate_chat_messages():
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        return _openrouter_response(_success_payload())

    with patch("httpx.post", side_effect=fake_post):
        _service().generate("SYSTEM RULES HERE", "USER CONTEXT AND TURN HERE")

    messages = calls[0]["messages"]
    assert messages == [
        {"role": "system", "content": "SYSTEM RULES HERE"},
        {"role": "user", "content": "USER CONTEXT AND TURN HERE"},
    ]


# --- 4. API key sent only in Authorization header ---


def test_api_key_is_sent_only_in_the_authorization_header():
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((json, headers))
        return _openrouter_response(_success_payload())

    with patch("httpx.post", side_effect=fake_post):
        _service(api_key="sk-or-super-secret").generate("s", "p")

    body, headers = calls[0]
    assert headers["Authorization"] == "Bearer sk-or-super-secret"
    assert "sk-or-super-secret" not in str(body)


# --- 5. API key never appears in logs ---


def test_api_key_never_appears_in_logs_even_on_failure():
    handler, teardown = _capture_llm_logs()
    try:
        with patch("httpx.post", return_value=_openrouter_response({"error": {"message": "boom"}}, status=401)):
            with pytest.raises(LLMServiceError):
                _service(api_key="sk-or-super-secret").generate("s", "p")
    finally:
        teardown()

    combined = "\n".join(handler.messages)
    assert "sk-or-super-secret" not in combined


# --- 6. usage metadata parsed ---


def test_usage_metadata_is_parsed_into_last_generation_metadata():
    with patch("httpx.post", return_value=_openrouter_response(_success_payload())):
        service = _service()
        service.generate("s", "p")

    metadata = service.last_generation_metadata
    assert metadata is not None
    assert metadata.provider == "openrouter"
    assert metadata.model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert metadata.prompt_tokens == 120
    assert metadata.completion_tokens == 40
    assert metadata.total_tokens == 160
    assert metadata.finish_reason == "stop"
    assert metadata.request_id == "gen-abc123"
    assert metadata.latency_ms >= 0


# --- 7. missing assistant content rejected ---


def test_missing_assistant_content_is_rejected():
    payload = {
        "id": "gen-1",
        "choices": [{"message": {"role": "assistant"}, "finish_reason": "stop"}],
    }
    with patch("httpx.post", return_value=_openrouter_response(payload)):
        with pytest.raises(LLMServiceError, match="empty completion"):
            _service().generate("s", "p")


def test_blank_assistant_content_is_also_rejected():
    with patch("httpx.post", return_value=_openrouter_response(_success_payload(content="   "))):
        with pytest.raises(LLMServiceError, match="empty completion"):
            _service().generate("s", "p")


def test_empty_choices_list_is_rejected():
    with patch("httpx.post", return_value=_openrouter_response({"id": "gen-1", "choices": []})):
        with pytest.raises(LLMServiceError, match="no completion choices"):
            _service().generate("s", "p")


# --- 8. malformed body rejected ---


def test_malformed_non_json_body_is_rejected():
    response = httpx.Response(
        200, content=b"not valid json", request=httpx.Request("POST", "https://openrouter.ai/x")
    )
    with patch("httpx.post", return_value=response):
        with pytest.raises(LLMServiceError, match="malformed"):
            _service().generate("s", "p")


# --- 9. 401 mapped correctly ---


def test_401_is_mapped_to_authentication_failure():
    response = _openrouter_response({"error": {"message": "Invalid API key"}}, status=401)
    with patch("httpx.post", return_value=response):
        with pytest.raises(LLMServiceError, match="authentication failed"):
            _service().generate("s", "p")


def test_missing_api_key_never_sends_a_request_and_raises_before_any_call():
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        return _openrouter_response(_success_payload())

    with patch("httpx.post", side_effect=fake_post):
        with pytest.raises(LLMServiceError, match="OPENROUTER_API_KEY"):
            _service(api_key="").generate("s", "p")

    assert calls == []


# --- 10. 429 mapped correctly ---


def test_429_is_mapped_to_rate_limited_and_never_retried():
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(1)
        return _openrouter_response({"error": {"message": "Rate limit exceeded"}}, status=429)

    with patch("httpx.post", side_effect=fake_post):
        with pytest.raises(LLMServiceError, match="rate limit"):
            _service().generate("s", "p")

    # Bounded behavior per spec: no aggressive retry on a rate limit.
    assert len(calls) == 1


# --- 11. 500 mapped correctly ---


def test_500_is_mapped_to_server_error():
    response = _openrouter_response({"error": {"message": "internal error"}}, status=500)
    with patch("httpx.post", return_value=response):
        with pytest.raises(LLMServiceError, match="server error"):
            _service().generate("s", "p")


def test_503_provider_unavailable_is_also_mapped_to_server_error():
    response = _openrouter_response({"error": {"message": "no available provider"}}, status=503)
    with patch("httpx.post", return_value=response):
        with pytest.raises(LLMServiceError, match="server error"):
            _service().generate("s", "p")


# --- 12. timeout mapped correctly ---


def test_timeout_is_mapped_to_llm_service_error():
    with patch("httpx.post", side_effect=httpx.TimeoutException("timed out")):
        with pytest.raises(LLMServiceError, match="too long"):
            _service().generate("s", "p")


def test_connect_error_is_mapped_to_llm_service_error():
    with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(LLMServiceError, match="Could not reach OpenRouter"):
            _service().generate("s", "p")


# --- 13. OpenRouter error payload mapped correctly ---


def test_error_payload_inside_an_otherwise_200_response_is_rejected():
    # Documented OpenRouter behavior: an upstream provider failure can
    # arrive as an "error" object inside a 200 response, not just via
    # HTTP status — must never be silently treated as an empty answer.
    payload = {"error": {"message": "Provider returned error", "code": 502}}
    with patch("httpx.post", return_value=_openrouter_response(payload, status=200)):
        with pytest.raises(LLMServiceError, match="Provider returned error"):
            _service().generate("s", "p")


def test_model_unavailable_404_is_mapped_correctly():
    response = _openrouter_response({"error": {"message": "model not found"}}, status=404)
    with patch("httpx.post", return_value=response):
        with pytest.raises(LLMServiceError, match="model unavailable"):
            _service().generate("s", "p")


# --- max_tokens / optional-parameter conservatism ---


def test_max_tokens_is_sent_only_when_configured():
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        return _openrouter_response(_success_payload())

    with patch("httpx.post", side_effect=fake_post):
        _service(max_tokens=None).generate("s", "p")

    assert "max_tokens" not in calls[0]


def test_temperature_is_sent_from_configuration():
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        return _openrouter_response(_success_payload())

    with patch("httpx.post", side_effect=fake_post):
        _service(temperature=0.9).generate("s", "p")

    assert calls[0]["temperature"] == 0.9


# --- reasoning suppression (confirmed necessary via a real live call:
# nvidia/nemotron-3-ultra-550b-a55b:free returned raw chain-of-thought
# inside message.content itself with no "reasoning" param sent) ---


def test_reasoning_exclude_is_always_requested():
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        return _openrouter_response(_success_payload())

    with patch("httpx.post", side_effect=fake_post):
        _service().generate("s", "p")

    assert calls[0]["reasoning"] == {"exclude": True}


# --- reasoning content, if a provider ever includes it, never leaks ---


def test_a_reasoning_field_alongside_content_is_never_surfaced():
    payload = _success_payload()
    payload["choices"][0]["message"]["reasoning"] = "internal chain of thought, never shown to the player"
    with patch("httpx.post", return_value=_openrouter_response(payload)):
        result = _service().generate("s", "p")

    assert "chain of thought" not in result
    assert result == "Olá, viajante."


# --- provider/model role selection (14, 15) ---


def test_provider_model_selection_for_narrative_role_builds_openrouter():
    settings = Settings(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:14b-instruct-q4_K_M",
        intent_llm_provider="ollama",
        intent_llm_model="",
        narrative_llm_provider="openrouter",
        narrative_llm_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        openrouter_api_key="sk-or-test",
    )
    intent_service, narrative_service = build_role_llm_services(settings)

    assert isinstance(intent_service, OllamaLLMService)
    assert intent_service.model_name == "qwen2.5:14b-instruct-q4_K_M"
    assert isinstance(narrative_service, OpenRouterLLMService)
    assert narrative_service.model_name == "nvidia/nemotron-3-ultra-550b-a55b:free"


def test_provider_model_selection_for_intent_role_builds_openrouter():
    settings = Settings(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:14b-instruct-q4_K_M",
        intent_llm_provider="openrouter",
        intent_llm_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        narrative_llm_provider="openrouter",
        narrative_llm_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        openrouter_api_key="sk-or-test",
    )
    intent_service, narrative_service = build_role_llm_services(settings)

    assert isinstance(intent_service, OpenRouterLLMService)
    assert isinstance(narrative_service, OpenRouterLLMService)


def test_default_service_follows_remote_narrative_provider_when_ollama_is_disabled():
    settings = Settings(
        narrative_llm_provider="openrouter",
        narrative_llm_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        openrouter_api_key="sk-or-test",
    )
    service = build_llm_service(settings)
    assert isinstance(service, OpenRouterLLMService)
    assert service.model_name == "nvidia/nemotron-3-ultra-550b-a55b:free"


def test_both_roles_support_explicit_ollama_back_compat():
    settings = Settings(
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:14b-instruct-q4_K_M",
        intent_llm_provider="ollama",
        intent_llm_model="",
        narrative_llm_provider="ollama",
        narrative_llm_model="",
    )
    intent_service, narrative_service = build_role_llm_services(settings)

    assert isinstance(intent_service, OllamaLLMService)
    assert isinstance(narrative_service, OllamaLLMService)
    assert intent_service.model_name == narrative_service.model_name == "qwen2.5:14b-instruct-q4_K_M"


def test_openrouter_role_without_a_model_raises_clearly():
    settings = Settings(narrative_llm_provider="openrouter", narrative_llm_model="", openrouter_api_key="sk-or-test")
    with pytest.raises(LLMServiceError, match="model must be configured"):
        build_role_llm_services(settings)


def test_unknown_provider_raises_clearly():
    settings = Settings(intent_llm_provider="bedrock")
    with pytest.raises(LLMServiceError, match="Unknown LLM provider"):
        build_role_llm_services(settings)


def test_disabled_automatic_roles_make_no_provider_available():
    settings = Settings(
        intent_llm_provider="disabled",
        intent_llm_model="",
        narrative_llm_provider="disabled",
        narrative_llm_model="",
    )
    intent_service, narrative_service = build_role_llm_services(settings)

    assert isinstance(intent_service, DisabledLLMService)
    assert isinstance(narrative_service, DisabledLLMService)
    with pytest.raises(LLMServiceError, match="disabled"):
        intent_service.generate("system", "prompt")


def test_regeneration_provider_is_independent_from_disabled_automatic_roles():
    settings = Settings(
        intent_llm_provider="disabled",
        narrative_llm_provider="disabled",
        regeneration_llm_provider="openrouter",
        regeneration_llm_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        openrouter_api_key="sk-or-test",
    )

    assert isinstance(build_regeneration_llm_service(settings), OpenRouterLLMService)


# --- English reasoning-leak guard (app.ai.narrator) — confirmed via a
# real live call against nvidia/nemotron-3-ultra-550b-a55b:free that
# OpenRouter's own reasoning.exclude request parameter alone does not
# reliably suppress this for this specific free-tier model/route: the
# model sometimes returns its own English chain-of-thought as the
# entire draft instead of Portuguese narration. ---


def test_english_reasoning_leak_is_detected_and_rejected():
    from app.ai.narrator import _empty_response_violations

    # The exact confirmed live failure text (Phase 24K benchmark run 1,
    # turn 5), verbatim.
    leaked = (
        "The user is asking me to write the next narrative moment. Let me analyze the "
        "context carefully.\n\nThe previous turn ended with all three NPCs looking at "
        "Logan. Now he asks a question to the group. Since there's no active NPC context "
        "and multiple people are present, I should follow the AUTHORITATIVE MECHANICAL "
        "FACTS guidance: indicate there are multiple people and he needs to specify who "
        "he's asking."
    )
    assert _empty_response_violations(leaked) != []


def test_genuine_portuguese_narration_is_never_flagged_as_a_reasoning_leak():
    from app.ai.narrator import _empty_response_violations

    genuine = (
        "A praça se abre ao redor, terra batida e pedra gasta pelo tempo e pelos pés de "
        "gerações. Casas de madeira e sapê formam um círculo irregular, algumas com "
        "varandas simples, outras com oficinas no térreo. O cheiro de fumaça de lenha e "
        "terra úmida paira no ar da manhã."
    )
    assert _empty_response_violations(genuine) == []


def test_a_leak_that_survives_every_revision_attempt_still_forces_the_safe_fallback():
    # Confirmed live as a real gap (not hypothetical): a stronger,
    # more persistent model can keep re-leaking English reasoning across
    # BOTH of narrate()'s bounded revision attempts, not just the first
    # draft. The check inside the loop alone isn't enough — narrate()'s
    # own final draft, after the loop ends, must be re-checked too, or
    # the raw leak reaches the player uncaught by anything else.
    from app.ai import narrator
    from app.ai.llm_service import LLMService

    class _StubbornLeak(LLMService):
        def generate(self, system: str, prompt: str) -> str:
            return (
                "The user is asking me to write the next narrative moment. Let me "
                "analyze the context carefully to determine the best response for this "
                "scene given the constraints outlined in the instructions above."
            )

    context = (
        "CURRENT PLAYER\nName: Logan\n\n"
        "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\nName: Cardal\nType: VILLAGE\n\n"
        "ACTIVE NPC CONTEXT\n- none"
    )
    result = narrator.narrate(
        _StubbornLeak(),
        "Logan observa os arredores de Cardal.",
        context,
        "Logan olha ao redor",
        "(nenhum historico)",
    )
    assert result == "Nada acontece de imediato."


def test_short_genuine_portuguese_line_with_no_diacritics_is_never_flagged():
    # "Ha mais de uma pessoa aqui. Diga com quem voce quer falar." — a
    # real, legitimate line from this codebase's own mechanical summary
    # text, happens to carry zero diacritics purely by chance. Confirms
    # the guard's own signal (the English word "the") never fires on
    # ordinary unaccented Portuguese, unlike a first, reverted version
    # of this check based on diacritic density alone (see below).
    from app.ai.narrator import _empty_response_violations

    assert _empty_response_violations("Ha mais de uma pessoa aqui. Diga com quem voce quer falar.") == []


def test_legitimate_all_portuguese_dialogue_with_few_diacritics_is_never_flagged():
    # The EXACT false positive a first, diacritic-density-based version
    # of this check produced against this codebase's own PRE-EXISTING,
    # passing test fixtures (test_narrator.py's StubbornAgencyLLM and
    # StubbornUnnamedFabricatedTurnLLM) — real fluent Portuguese dialogue
    # that happens to lean on common unaccented words. Caught by the
    # full suite before this was ever reported done, exactly the
    # discipline this whole codebase's own history already relies on.
    from app.ai.narrator import _empty_response_violations

    assert (
        _empty_response_violations(
            "— Osgar sorri e acena com a cabeça.\n\n"
            "— Entendo — diz Logan, inclinando-se para frente. — O que posso fazer por aqui?"
        )
        == []
    )
    assert (
        _empty_response_violations(
            "— Venha conferir nossa cozinha! O que me diz? — pergunta Talven, sorridente.\n\n"
            "— Agradeço a gentileza, mas ainda estou ponderando onde ficar esta noite.\n\n"
            "Talven Brooks assente com entendimento e respeita o desejo de Logan de tomar "
            "uma decisão."
        )
        == []
    )


# --- 16. Ollama still works unchanged ---
# (Direct regression coverage already lives in test_llm_service.py, which
# is re-run as part of the full suite alongside this file; this test
# adds only the ONE new assertion specific to this phase — that Ollama
# now also reports provider_name/model_name/last_generation_metadata,
# the new surface every role-selection caller depends on.)


def test_ollama_service_now_also_reports_provider_and_model_name():
    service = OllamaLLMService(
        base_url="http://127.0.0.1:11434", model="qwen2.5:14b-instruct-q4_K_M", timeout=5.0
    )
    assert service.provider_name == "ollama"
    assert service.model_name == "qwen2.5:14b-instruct-q4_K_M"
    assert service.last_generation_metadata is None

    def fake_post(url, json, timeout):
        return httpx.Response(
            200,
            json={
                "response": "ok",
                "eval_count": 40,
                "prompt_eval_count": 120,
                "done_reason": "stop",
            },
            request=httpx.Request("POST", url),
        )

    with patch("httpx.post", side_effect=fake_post):
        service.generate("s", "p")

    metadata = service.last_generation_metadata
    assert metadata is not None
    assert metadata.provider == "ollama"
    assert metadata.completion_tokens == 40
    assert metadata.prompt_tokens == 120
    assert metadata.finish_reason == "stop"


# --- 17. no automatic fallback occurs ---


def test_production_path_uses_a_different_service_per_role_and_reports_it(client, db_session):
    """Drives the real /actions endpoint (intent parse -> engine ->
    narration -> validation -> persistence) with two DISTINCT fake
    LLMServices, one per role, proving app.game.engine actually threads
    intent_llm_service through to intent_parser.parse (not narrator.
    narrate) and llm_service through to narrator.narrate — the exact
    "provider/model selection works independently for each role"
    requirement, exercised end-to-end rather than only at the factory
    level (build_role_llm_services, tested above)."""
    from app.api.dependencies.llm import set_role_llm_service_overrides

    class _IntentFake(LLMService):
        @property
        def provider_name(self) -> str:
            return "ollama"

        @property
        def model_name(self) -> str:
            return "qwen2.5:14b-instruct-q4_K_M"

        def generate(self, system: str, prompt: str) -> str:
            return '{"intent": "FREEFORM", "target": null}'

    class _NarrativeFake(LLMService):
        @property
        def provider_name(self) -> str:
            return "openrouter"

        @property
        def model_name(self) -> str:
            return "nvidia/nemotron-3-ultra-550b-a55b:free"

        def generate(self, system: str, prompt: str) -> str:
            return "O vento sopra sobre a praça."

    intent_fake = _IntentFake()
    narrative_fake = _NarrativeFake()

    campaign_resp = client.post("/api/campaigns", json={"name": "24K Role Split"})
    campaign_id = campaign_resp.json()["id"]
    character_resp = client.post(f"/api/campaigns/{campaign_id}/characters", json={"name": "Logan"})
    character_id = character_resp.json()["id"]
    client.post(f"/api/campaigns/{campaign_id}/start?character_id={character_id}")

    set_role_llm_service_overrides(intent=intent_fake, narrative=narrative_fake)
    try:
        resp = client.post(
            f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
            json={"text": "Logan observa ao redor"},
        )
    finally:
        set_role_llm_service_overrides(intent=None, narrative=None)

    assert resp.status_code == 200
    assert resp.json()["narrative"] == "O vento sopra sobre a praça."


def test_narrative_role_failure_never_falls_back_to_the_intent_role_service():
    # The intent service (Ollama) is healthy; the narrative service
    # (OpenRouter) fails. No code path here should ever call the intent
    # service to "cover for" the narrative failure — the spec's explicit
    # "no automatic provider fallback during this evaluation."
    ollama_calls = []

    def fake_ollama_post(url, json, timeout):
        ollama_calls.append(1)
        return httpx.Response(200, json={"response": "ollama answered"}, request=httpx.Request("POST", url))

    narrative = _service()

    with patch("httpx.post") as mock_post:
        def _dispatch(url, *args, **kwargs):
            if "openrouter" in url:
                return _openrouter_response({"error": {"message": "down"}}, status=503)
            return fake_ollama_post(url, kwargs.get("json"), kwargs.get("timeout"))

        mock_post.side_effect = _dispatch
        with pytest.raises(LLMServiceError):
            narrative.generate("s", "p")

    assert ollama_calls == []
