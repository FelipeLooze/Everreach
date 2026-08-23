"""Phase 23D-Q / 23D-Q.2 — GPU Resource Coordination: Ollama side."""
from unittest.mock import patch

import httpx
import pytest

from app.ai.llm_service import LLMService, OllamaLLMService, build_llm_service
from app.core.config import Settings
from app.core.gpu_coordinator import _lock, set_llm_release_hook


def _service() -> OllamaLLMService:
    return OllamaLLMService(
        base_url="http://127.0.0.1:11434", model="test-model", timeout=5.0,
        embedding_model="test-embed-model",
    )


def _json_response(payload, url="http://x") -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("POST", url))


def test_generate_holds_the_gpu_coordinator_lock_during_the_request():
    locked_during_call = []

    def fake_post(url, json, timeout):
        locked_during_call.append(_lock.locked())
        return _json_response({"response": "ok"})

    with patch("httpx.post", side_effect=fake_post):
        result = _service().generate("system", "prompt")

    assert result == "ok"
    assert locked_during_call == [True]
    assert not _lock.locked()


def test_embed_holds_the_gpu_coordinator_lock_during_the_request():
    locked_during_call = []

    def fake_post(url, json, timeout):
        locked_during_call.append(_lock.locked())
        return _json_response({"embeddings": [[0.1, 0.2, 0.3]]})

    with patch("httpx.post", side_effect=fake_post):
        result = _service().embed("some text")

    assert result == [0.1, 0.2, 0.3]
    assert locked_during_call == [True]
    assert not _lock.locked()


def test_generate_releases_the_lock_even_when_ollama_errors():
    with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
        try:
            _service().generate("system", "prompt")
        except Exception:
            pass

    assert not _lock.locked()


@pytest.fixture(autouse=True)
def _reset_llm_release_hook():
    yield
    set_llm_release_hook(None)


def test_base_llm_service_release_gpu_residency_defaults_to_a_safe_no_op():
    class _Minimal(LLMService):
        def generate(self, system: str, prompt: str) -> str:
            return "x"

    _Minimal().release_gpu_residency()  # must not raise


def test_release_gpu_residency_sends_a_zero_keep_alive_request():
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return _json_response({})

    with patch("httpx.post", side_effect=fake_post):
        _service().release_gpu_residency()

    assert len(calls) == 1
    url, payload = calls[0]
    assert url == "http://127.0.0.1:11434/api/generate"
    assert payload["model"] == "test-model"
    assert payload["keep_alive"] == 0


def test_release_gpu_residency_swallows_errors_silently():
    with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
        _service().release_gpu_residency()  # must not raise


def test_build_llm_service_registers_the_release_hook_with_the_coordinator():
    from app.core.gpu_coordinator import gpu_heavy_operation

    settings = Settings(
        ollama_base_url="http://127.0.0.1:11434", ollama_model="test-model",
        ollama_timeout_seconds=5.0,
    )
    service = build_llm_service(settings)

    calls = []

    def fake_post(url, json, timeout):
        calls.append(json)
        return _json_response({})

    with patch("httpx.post", side_effect=fake_post):
        with gpu_heavy_operation("VISUAL_TASK"):
            pass

    assert len(calls) == 1
    assert calls[0]["keep_alive"] == 0
    assert isinstance(service, OllamaLLMService)
