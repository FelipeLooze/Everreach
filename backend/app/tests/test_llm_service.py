"""Phase 23D-Q — GPU Resource Coordination: Ollama side."""
from unittest.mock import patch

import httpx

from app.ai.llm_service import OllamaLLMService
from app.core.gpu_coordinator import _lock


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
