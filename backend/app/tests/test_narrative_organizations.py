"""Phase 19L — Organization / Social Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.core.enums import CombatActorType, OrganizationOrigin, OrganizationType
from app.game.character.service import create_character
from app.game.organizations.roles import join_organization
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign


def _proposal(text: str, *, character_id, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu me apresento.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
        character_id=character_id,
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_claimed_membership_without_actual_membership_is_rejected(db_session):
    campaign = create_campaign(db_session, "Associacao Falsa")
    character = create_character(db_session, campaign.id, "Logan")
    create_organization(
        db_session, campaign.id, "Guilda dos Mercadores",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )

    proposal = _proposal(
        "Como membro da Guilda dos Mercadores, você recebe um desconto especial.",
        character_id=character.id,
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_claimed_membership_with_actual_membership_is_allowed(db_session):
    campaign = create_campaign(db_session, "Associacao Real")
    character = create_character(db_session, campaign.id, "Logan")
    organization = create_organization(
        db_session, campaign.id, "Guilda dos Mercadores",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    join_organization(db_session, organization, CombatActorType.CHARACTER, character.id)

    proposal = _proposal(
        "Como membro da Guilda dos Mercadores, você recebe um desconto especial.",
        character_id=character.id,
        context="CURRENT PLAYER\nName: Logan\n\nKNOWN ORGANIZATIONS\n- Guilda dos Mercadores",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_membership_claim_for_an_unknown_organization_name_is_never_guessed_at(db_session):
    campaign = create_campaign(db_session, "Organizacao Desconhecida")
    character = create_character(db_session, campaign.id, "Logan")

    proposal = _proposal(
        "Como membro da Ordem Inexistente, você é bem-vindo aqui.",
        character_id=character.id,
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_narration_with_no_membership_claim_is_never_checked(db_session):
    campaign = create_campaign(db_session, "Sem Reivindicacao De Associacao")
    character = create_character(db_session, campaign.id, "Logan")

    proposal = _proposal("O sol se põe no horizonte distante.", character_id=character.id)

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
