"""Phase 19O — Persistent Content Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.game.world.seed import create_campaign


def _proposal(text: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu escuto.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_inventing_a_secret_family_relationship_is_rejected(db_session):
    campaign = create_campaign(db_session, "Parentesco Inventado")
    proposal = _proposal("O ferreiro tem uma filha secreta chamada Elena.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_relationship_already_established_in_context_is_allowed(db_session):
    campaign = create_campaign(db_session, "Parentesco Ja Estabelecido")
    proposal = _proposal(
        "A filha do ferreiro cumprimenta os visitantes.",
        context="CURRENT PLAYER\nName: Logan\n\nACTIVE NPC CONTEXT\nOsgar tem uma filha chamada Elena.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_narration_with_no_persistent_relationship_claim_is_allowed(db_session):
    campaign = create_campaign(db_session, "Sem Reivindicacao Persistente")
    proposal = _proposal("A brisa da tarde balança as folhas das árvores.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
