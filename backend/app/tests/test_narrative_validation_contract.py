"""Phase 19A — Narrative Validation Contract."""

from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.ai.validation.contract import NarrativeProposal, validate_narrative_proposal
from app.core.enums import ActionIntentType
from app.game import engine
from app.game.character.service import create_character
from app.game.world.seed import create_campaign, seed_initial_region


def _proposal(text: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="Logan descansa.",
        player_input="Eu descanso.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_validate_narrative_proposal_is_a_pass_through_today(db_session):
    """Phase 19A introduces only the seam, no validators — this pins that
    baseline so a future subphase (19D+) that starts rejecting/repairing
    text is a deliberate, visible change to this test, not silent drift."""
    campaign = create_campaign(db_session, "Contrato De Validacao")
    proposal = _proposal("O vento frio corta pelo vale.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
    assert result.final_text == proposal.text
    assert result.violations == []


def test_ordinary_sensory_narration_is_not_rejected(db_session):
    """Foundation for Phase 19E: atmospheric/sensory prose — exactly the
    kind of narration the spec explicitly wants preserved — must not be
    flagged by the seam introduced here. Currently true because nothing
    is validated yet; this test exists so 19E's real sensory policy is
    written against a known-passing baseline, not a guess."""
    campaign = create_campaign(db_session, "Narracao Sensorial")
    proposal = _proposal(
        "O ar frio da manhã arde na pele exposta. Ao longe, o martelo do "
        "ferreiro soa em ritmo constante, misturado ao cheiro de pão fresco."
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
    assert result.final_text == proposal.text


def test_unsupported_voluntary_protagonist_action_is_not_yet_rejected(db_session):
    """Documents the CURRENT (pre-19D) baseline for a PLAYER_VOLUNTARY-
    shaped claim the player never caused ("Logan sorri e abraça Osgar")
    — the contract itself does not judge agency yet; app.ai.narrator's
    own existing regex-based agency checks are a separate, already-
    working layer (unaffected by this module). Phase 19D will replace
    this pass-through with a real check; when it does, this test's
    expected result should change alongside it — it is not a
    correctness guarantee today, only a documented starting point."""
    campaign = create_campaign(db_session, "Agencia Ainda Nao Validada")
    proposal = _proposal(
        "Logan sorri e abraça Osgar.", player_input="Eu descanso."
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
    assert result.final_text == "Logan sorri e abraça Osgar."


def test_narrative_proposal_carries_active_npc_identity_when_present(db_session):
    proposal = _proposal(
        "Osgar acena.", active_npc_id="npc_fake", active_npc_name="Osgar",
    )

    assert proposal.active_npc_id == "npc_fake"
    assert proposal.active_npc_name == "Osgar"


def test_narrative_proposal_defaults_active_npc_fields_to_none():
    proposal = _proposal("Nada acontece.")

    assert proposal.active_npc_id is None
    assert proposal.active_npc_name is None


def test_engine_resolve_action_routes_narration_through_the_new_seam_unchanged(
    db_session, monkeypatch
):
    """End-to-end proof the Phase 19A wiring in app.game.engine is live
    and, being a pass-through today, changes nothing about what the
    player actually sees — the exact behavior-preservation the FIRST
    TASK instructions require."""

    class _FixedTextLLM(LLMService):
        def generate(self, system: str, prompt: str) -> str:
            return "O tempo passa devagar enquanto nada de extraordinário acontece."

    campaign = create_campaign(db_session, "Selo De Validacao Ponta A Ponta")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)

    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *_args, **_kwargs: Intent(
            type=ActionIntentType.FREEFORM, target=None, raw_text="Eu observo o vale."
        ),
    )

    result = engine.resolve_action(
        db_session, _FixedTextLLM(), campaign.id, character.id,
        "Eu observo o vale.", action_key="freeform-001",
    )

    assert result.narrative == "O tempo passa devagar enquanto nada de extraordinário acontece."
