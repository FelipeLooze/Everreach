"""Phase 19I — Character Capability Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.game.world.seed import create_campaign


def _proposal(text: str, mechanical_summary: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary=mechanical_summary,
        player_input="Eu tento escalar o muro.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_claimed_success_contradicting_a_resolved_failure_is_rejected(db_session):
    campaign = create_campaign(db_session, "Sucesso Inventado")
    proposal = _proposal(
        "O muro é alto, mas você consegue escalar com facilidade.",
        mechanical_summary="Logan tenta escalar o muro e falha.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_narration_matching_a_resolved_failure_is_allowed(db_session):
    campaign = create_campaign(db_session, "Falha Narrada Corretamente")
    proposal = _proposal(
        "As mãos escorregam pela pedra úmida e o muro permanece intransponível.",
        mechanical_summary="Logan tenta escalar o muro e falha.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_narration_matching_a_resolved_success_is_allowed(db_session):
    campaign = create_campaign(db_session, "Sucesso Narrado Corretamente")
    proposal = _proposal(
        "Você consegue escalar o muro sem dificuldade.",
        mechanical_summary="Logan tenta escalar o muro e consegue.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_narration_underselling_a_resolved_success_is_not_rejected(db_session):
    """Only invented success is rejected — undersold prose after an
    actual success is weaker writing, not a capability violation."""
    campaign = create_campaign(db_session, "Sucesso Subestimado Nao Rejeitado")
    proposal = _proposal(
        "O muro continua alto à sua frente.",
        mechanical_summary="Logan tenta escalar o muro e consegue.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
