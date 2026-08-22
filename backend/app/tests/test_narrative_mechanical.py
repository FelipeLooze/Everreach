"""Phase 19N — Mechanical Outcome Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.game.world.seed import create_campaign


def _proposal(text: str, mechanical_summary: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary=mechanical_summary,
        player_input="Eu ataco.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_severe_narration_of_a_grazing_hit_is_rejected(db_session):
    campaign = create_campaign(db_session, "Intensidade Exagerada")
    proposal = _proposal(
        "A lâmina esmaga o adversário, destroçando seu corpo por completo.",
        mechanical_summary="O golpe acerta de leve, sem gravidade.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_proportional_narration_of_a_grazing_hit_is_allowed(db_session):
    campaign = create_campaign(db_session, "Intensidade Proporcional")
    proposal = _proposal(
        "A lâmina roça de leve o braço do adversário, sem causar dano sério.",
        mechanical_summary="O golpe acerta de leve, sem gravidade.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_severe_narration_after_a_genuinely_severe_outcome_is_allowed(db_session):
    campaign = create_campaign(db_session, "Resultado Realmente Grave")
    proposal = _proposal(
        "O golpe esmaga a defesa do adversário com força brutal.",
        mechanical_summary="O golpe acerta com força total, causando um ferimento grave.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_understated_narration_of_a_severe_outcome_is_not_rejected(db_session):
    """Only escalation (minor -> severe) is rejected — underselling a
    genuinely severe outcome is weaker prose, not invented harm."""
    campaign = create_campaign(db_session, "Resultado Grave Subestimado Nao Rejeitado")
    proposal = _proposal(
        "O golpe acerta o adversário.",
        mechanical_summary="O golpe acerta com força total, causando um ferimento grave.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
