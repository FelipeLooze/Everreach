"""Phase 19M — Temporal Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.core.enums import OrganizationOrigin, OrganizationStatus, OrganizationType
from app.ai.retrieval.canon import index_organization
from app.game.organizations.service import create_organization, set_organization_status
from app.game.world.seed import create_campaign


def _proposal(text: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu pergunto sobre a guilda.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_narration_asserting_a_superseded_status_is_rejected(db_session):
    campaign = create_campaign(db_session, "Status Desatualizado")
    organization = create_organization(
        db_session, campaign.id, "Guilda dos Ferreiros",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    index_organization(db_session, organization)
    set_organization_status(db_session, organization, OrganizationStatus.DISBANDED)

    proposal = _proposal(
        "A Guilda dos Ferreiros permanece ativa e recebe novos membros toda semana.",
        context="CURRENT PLAYER\nName: Logan\n\nKNOWN ORGANIZATIONS\n- Guilda dos Ferreiros",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_narration_asserting_the_current_status_is_allowed(db_session):
    campaign = create_campaign(db_session, "Status Atual")
    organization = create_organization(
        db_session, campaign.id, "Guilda dos Ferreiros",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    index_organization(db_session, organization)
    set_organization_status(db_session, organization, OrganizationStatus.DISBANDED)

    proposal = _proposal(
        "A Guilda dos Ferreiros foi dissolvida há algum tempo.",
        context="CURRENT PLAYER\nName: Logan\n\nKNOWN ORGANIZATIONS\n- Guilda dos Ferreiros",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_organization_never_superseded_has_nothing_to_check(db_session):
    campaign = create_campaign(db_session, "Sem Historico")
    create_organization(
        db_session, campaign.id, "Guilda dos Ferreiros",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )

    proposal = _proposal(
        "A Guilda dos Ferreiros permanece ativa.",
        context="CURRENT PLAYER\nName: Logan\n\nKNOWN ORGANIZATIONS\n- Guilda dos Ferreiros",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
