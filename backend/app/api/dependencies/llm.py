from functools import lru_cache

from app.ai.llm_service import LLMService, build_llm_service

_override: LLMService | None = None


def set_llm_service_override(service: LLMService | None) -> None:
    """Test hook: inject a fake LLMService instead of talking to real Ollama."""
    global _override
    _override = service


@lru_cache
def _cached_default() -> LLMService:
    return build_llm_service()


def get_llm_service() -> LLMService:
    if _override is not None:
        return _override
    return _cached_default()
