"""Phase 19F — Canon Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.game.world.seed import create_campaign


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


def test_persistent_concept_unsupported_by_context_is_rejected(db_session):
    campaign = create_campaign(db_session, "Conceito Sem Suporte")
    proposal = _proposal("Uma ponte antiga cruza o rio logo ali.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False
    assert result.violations


def test_persistent_concept_already_present_in_context_is_allowed(db_session):
    campaign = create_campaign(db_session, "Conceito Ja Suportado")
    proposal = _proposal(
        "A ponte de pedra permanece firme e sólida.",
        context="CURRENT PLAYER\nName: Logan\n\nCANONICAL LOCATION CONTEXT\nUma ponte de pedra liga as duas margens.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_quantified_history_without_canonical_support_is_rejected(db_session):
    campaign = create_campaign(db_session, "Historia Quantificada Sem Apoio")
    proposal = _proposal("Este lugar existe há cinquenta anos.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_ordinary_narration_with_no_canon_claims_passes(db_session):
    campaign = create_campaign(db_session, "Sem Reivindicacao De Canon")
    proposal = _proposal("A luz da manhã se espalha pela praça.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
