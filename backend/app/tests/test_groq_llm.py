from unittest.mock import patch

import httpx
import pytest

from app.ai.llm_service import (
    GroqLLMService,
    LLMServiceError,
    OpenRouterLLMService,
    build_role_llm_services,
)
from app.core.config import Settings


def _response(content: str = '{"intent":"EXAMINE","target":null}') -> httpx.Response:
    request = httpx.Request(
        "POST", "https://api.groq.com/openai/v1/chat/completions"
    )
    return httpx.Response(
        200,
        request=request,
        json={
            "id": "groq-request-1",
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 8,
                "total_tokens": 28,
            },
        },
    )


def test_groq_uses_chat_completions_without_openrouter_only_fields():
    service = GroqLLMService(
        api_key="gsk-test",
        model="openai/gpt-oss-20b",
    )

    with patch("httpx.post", return_value=_response()) as post:
        result = service.generate("Classifique.", "Olho ao redor.")

    assert result == '{"intent":"EXAMINE","target":null}'
    assert service.provider_name == "groq"
    assert service.model_name == "openai/gpt-oss-20b"
    assert service.last_generation_metadata is not None
    assert service.last_generation_metadata.provider == "groq"

    call = post.call_args
    assert call.args[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert call.kwargs["headers"]["Authorization"] == "Bearer gsk-test"
    assert call.kwargs["json"]["temperature"] == 0.0
    assert "reasoning" not in call.kwargs["json"]


def test_groq_requires_its_own_api_key_before_network_access():
    service = GroqLLMService(api_key="", model="openai/gpt-oss-20b")

    with patch("httpx.post") as post, pytest.raises(
        LLMServiceError, match="GROQ_API_KEY is not configured"
    ):
        service.generate("system", "prompt")

    post.assert_not_called()


def test_intent_can_use_groq_while_narrative_uses_openrouter():
    settings = Settings(
        intent_llm_provider="groq",
        intent_llm_model="openai/gpt-oss-20b",
        groq_api_key="gsk-test",
        narrative_llm_provider="openrouter",
        narrative_llm_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        openrouter_api_key="sk-or-test",
    )

    intent_service, narrative_service = build_role_llm_services(settings)

    assert isinstance(intent_service, GroqLLMService)
    assert isinstance(narrative_service, OpenRouterLLMService)


def test_groq_role_requires_an_explicit_model():
    settings = Settings(
        intent_llm_provider="groq",
        intent_llm_model="",
        groq_api_key="gsk-test",
    )

    with pytest.raises(LLMServiceError, match="Groq model must be configured"):
        build_role_llm_services(settings)
