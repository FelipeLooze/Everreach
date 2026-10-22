from unittest.mock import patch

import httpx
import pytest

from app.ai.llm_service import (
    FallbackLLMService,
    LLMRateLimitError,
    LLMService,
    LLMServiceError,
    NvidiaLLMService,
    build_regeneration_llm_service,
    build_role_llm_services,
)
from app.core.config import Settings


def _response(content: str = "A praça desperta.") -> httpx.Response:
    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    return httpx.Response(
        200,
        request=request,
        json={
            "id": "nvidia-request-1",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "reasoning_content": "Thinking in English about the square...",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 40, "completion_tokens": 9, "total_tokens": 49},
        },
    )


def test_nvidia_reads_only_content_and_sends_no_openrouter_fields():
    service = NvidiaLLMService(api_key="nvapi-test", model="nvidia/nemotron-3-ultra-550b-a55b")

    with patch("httpx.post", return_value=_response()) as post:
        result = service.generate("Narre.", "Olho ao redor.")

    assert result == "A praça desperta."
    assert service.provider_name == "nvidia"
    assert service.last_generation_metadata.provider == "nvidia"
    call = post.call_args
    assert call.args[0] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert call.kwargs["headers"]["Authorization"] == "Bearer nvapi-test"
    assert "reasoning" not in call.kwargs["json"]
    assert "chat_template_kwargs" not in call.kwargs["json"]


def test_nvidia_enable_thinking_goes_through_chat_template_kwargs():
    service = NvidiaLLMService(
        api_key="nvapi-test", model="nvidia/nemotron-3-ultra-550b-a55b", enable_thinking=False
    )

    with patch("httpx.post", return_value=_response()) as post:
        service.generate("Narre.", "Olho ao redor.")

    assert post.call_args.kwargs["json"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_nvidia_without_key_fails_before_any_request():
    service = NvidiaLLMService(api_key="", model="openai/gpt-oss-20b")

    with patch("httpx.post") as post, pytest.raises(LLMServiceError, match="NVIDIA_API_KEY"):
        service.generate("Classifique.", "Olho ao redor.")
    post.assert_not_called()


class _Scripted(LLMService):
    def __init__(self, provider: str, result):
        self._provider = provider
        self._result = result
        self.calls = 0

    def generate(self, system, prompt):
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    @property
    def provider_name(self):
        return self._provider

    @property
    def model_name(self):
        return f"{self._provider}-model"


def test_fallback_is_not_called_when_primary_answers():
    primary, fallback = _Scripted("groq", "ok"), _Scripted("nvidia", "unused")
    service = FallbackLLMService(primary, fallback)

    assert service.generate("s", "p") == "ok"
    assert fallback.calls == 0
    assert service.provider_name == "groq"


def test_fallback_answers_when_primary_is_rate_limited_and_reports_itself():
    primary = _Scripted("groq", LLMRateLimitError("daily tokens", retry_after_seconds=3600))
    fallback = _Scripted("nvidia", "ok")
    service = FallbackLLMService(primary, fallback)

    assert service.generate("s", "p") == "ok"
    assert service.provider_name == "nvidia"
    assert service.model_name == "nvidia-model"


def test_fallback_error_propagates_when_both_fail():
    primary = _Scripted("nvidia", LLMServiceError("down"))
    fallback = _Scripted("openrouter", LLMRateLimitError("free-models-per-day"))
    service = FallbackLLMService(primary, fallback)

    with pytest.raises(LLMRateLimitError):
        service.generate("s", "p")


def test_each_call_tries_the_primary_again():
    primary = _Scripted("nvidia", LLMServiceError("blip"))
    fallback = _Scripted("openrouter", "ok")
    service = FallbackLLMService(primary, fallback)

    service.generate("s", "p")
    primary._result = "back"

    assert service.generate("s", "p") == "back"
    assert service.provider_name == "nvidia"


def test_recommended_settings_build_each_role_with_its_fallback():
    settings = Settings(
        groq_api_key="gsk",
        nvidia_api_key="nvapi",
        openrouter_api_key="sk-or",
        intent_llm_provider="groq",
        intent_llm_model="openai/gpt-oss-20b",
        intent_llm_fallback_provider="nvidia",
        intent_llm_fallback_model="openai/gpt-oss-20b",
        narrative_llm_provider="nvidia",
        narrative_llm_model="nvidia/nemotron-3-ultra-550b-a55b",
        narrative_llm_fallback_provider="openrouter",
        narrative_llm_fallback_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        regeneration_llm_provider="nvidia",
        regeneration_llm_model="nvidia/nemotron-3-ultra-550b-a55b",
        regeneration_llm_fallback_provider="openrouter",
        regeneration_llm_fallback_model="nvidia/nemotron-3-ultra-550b-a55b:free",
    )

    intent, narrative = build_role_llm_services(settings)
    regeneration = build_regeneration_llm_service(settings)

    assert (intent.provider_name, intent._fallback.provider_name) == ("groq", "nvidia")
    assert intent._fallback._temperature == settings.nvidia_intent_temperature
    assert (narrative.provider_name, narrative._fallback.provider_name) == ("nvidia", "openrouter")
    assert narrative._primary._temperature == settings.nvidia_temperature
    assert regeneration.provider_name == "nvidia"


def test_no_fallback_configured_returns_the_plain_service():
    settings = Settings(
        groq_api_key="gsk",
        intent_llm_provider="groq",
        intent_llm_model="openai/gpt-oss-20b",
        narrative_llm_provider="disabled",
    )

    intent, _narrative = build_role_llm_services(settings)

    assert not isinstance(intent, FallbackLLMService)
