"""Phase 19S — Validation Trace & Observability."""

import logging

from app.ai.llm_service import LLMService
from app.ai.intent_parser import Intent
from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.ai.validation.claims import extract_claims
from app.ai.validation.trace import log_validation_trace
from app.core.enums import ActionIntentType
from app.core.logging import get_logger
from app.game import engine
from app.game.character.service import create_character
from app.game.world.seed import create_campaign, seed_initial_region


def _proposal(text: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu observo.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_log_validation_trace_never_raises_and_is_silent_above_debug_level(db_session, caplog):
    proposal = _proposal("Logan decide fugir.")
    claims = extract_claims(proposal.text, character_name=proposal.character_name)

    logger = get_logger("narration")
    original_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        log_validation_trace(proposal, claims, [])
    finally:
        logger.setLevel(original_level)

    assert not any("NARRATIVE VALIDATION TRACE" in record.message for record in caplog.records)


def test_log_validation_trace_at_debug_level_includes_claim_and_result():
    """Attaches a plain logging.Handler directly to the "narration"
    logger instead of relying on pytest's caplog (which captures via
    propagation to Python's root logger by default) — app.core.logging.
    configure_logging sets the "everreach" ancestor logger's
    propagate=False as soon as anything in the suite triggers app
    startup (e.g. the `client` fixture), so caplog silently sees
    nothing once that has happened anywhere earlier in the same test
    process. Also resets logging.Logger.manager.disable: some earlier
    test in the full suite (outside this module, not tracked down —
    likely a third-party test-client/logging interaction) leaves the
    process-wide logging.disable(...) ceiling raised, which makes
    isEnabledFor(DEBUG) return False regardless of this logger's own
    explicit level. Both are process-global state this test must not
    assume is at its default, and must restore afterward regardless."""
    proposal = _proposal("Logan decide fugir.")
    claims = extract_claims(proposal.text, character_name=proposal.character_name)

    records: list[str] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = get_logger("narration")
    handler = _ListHandler()
    original_level = logger.level
    original_disabled = logger.disabled
    original_disable = logging.Logger.manager.disable
    logging.disable(logging.NOTSET)
    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        log_validation_trace(proposal, claims, [])
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.disabled = original_disabled
        logging.disable(original_disable)

    messages = "\n".join(records)
    assert "NARRATIVE VALIDATION TRACE" in messages
    assert "Logan decide fugir." in messages
    assert "ALLOWED" in messages


def test_violation_reasons_never_reach_the_player_facing_action_result(db_session, monkeypatch):
    """Phase 19S's real fix: narrative_validation.violations must never
    end up in ActionResult.warnings, which schemas/action.py returns
    verbatim over the public /actions API. narrator.narrate() has its
    own internal agency-repair loop that would normally intercept an
    agency-violating draft before this pipeline even sees it, so
    validate_narrative_proposal itself is monkeypatched here to force a
    violation through — isolating exactly the engine.py integration
    point this subphase fixed, independent of narrator.py's own
    (already-tested, unaffected) internal defenses."""

    class _PassiveLLM(LLMService):
        def generate(self, system: str, prompt: str) -> str:
            return "O momento passa em silêncio."

    campaign = create_campaign(db_session, "Trace Nao Vaza Para Jogador")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)

    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *_args, **_kwargs: Intent(
            type=ActionIntentType.FREEFORM, target=None, raw_text="Eu olho ao redor."
        ),
    )

    from app.ai.validation.contract import NarrativeValidationResult

    monkeypatch.setattr(
        engine,
        "validate_narrative_proposal",
        lambda *_args, **_kwargs: NarrativeValidationResult(
            valid=False,
            final_text="O momento passa em silêncio.",
            violations=["'Logan decide fugir.' atribui uma ação voluntária não suportada."],
        ),
    )

    result = engine.resolve_action(
        db_session, _PassiveLLM(), campaign.id, character.id,
        "Eu olho ao redor.", action_key="trace-leak-001",
    )

    for warning in result.warnings:
        assert "atribui uma" not in warning
