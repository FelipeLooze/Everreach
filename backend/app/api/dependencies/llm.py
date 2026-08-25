from functools import lru_cache

from app.ai.llm_service import LLMService, build_llm_service, build_role_llm_services

_narrative_override: LLMService | None = None
_intent_override: LLMService | None = None


def set_llm_service_override(service: LLMService | None) -> None:
    """Test hook: inject a fake LLMService instead of talking to real
    providers. Sets BOTH the intent and narrative role to the SAME
    service — the pre-Phase-24K behavior every existing test already
    relies on (one fake standing in for the whole pipeline). Use
    set_role_llm_service_overrides for a role-specific override."""
    global _narrative_override, _intent_override
    _narrative_override = service
    _intent_override = service


def set_role_llm_service_overrides(
    *, intent: LLMService | None = None, narrative: LLMService | None = None
) -> None:
    """Phase 24K — override intent and narrative independently, e.g. to
    prove in a test that they really can be different providers. Passing
    None for a role clears just that role's override (falls back to the
    cached real service for that role only)."""
    global _narrative_override, _intent_override
    _intent_override = intent
    _narrative_override = narrative


@lru_cache
def _cached_default() -> LLMService:
    return build_llm_service()


@lru_cache
def _cached_role_defaults() -> tuple[LLMService, LLMService]:
    return build_role_llm_services()


def get_llm_service() -> LLMService:
    """Back-compat single-service accessor for callers unaffected by
    Phase 24K's intent/narrative role split (world-gen content helpers
    reached from outside app.game.engine's own dual-service wiring).
    Always resolves to the narrative-role service when the two differ."""
    if _narrative_override is not None:
        return _narrative_override
    return _cached_default()


def get_intent_llm_service() -> LLMService:
    if _intent_override is not None:
        return _intent_override
    return _cached_role_defaults()[0]


def get_narrative_llm_service() -> LLMService:
    if _narrative_override is not None:
        return _narrative_override
    return _cached_role_defaults()[1]
