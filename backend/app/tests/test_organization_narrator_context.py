"""Phase 13N — System / Narrator Context. Closes Phase 13 (13A-13N).

Only organizations the character is actually a member of, or PUBLIC ones
headquartered exactly where the character currently stands, ever appear
— a PRIVATE or SECRET organization existing elsewhere in the campaign
never leaks into context just because it exists. Reputation, membership,
and leader are all real, already-established facts (Phase 13F/13G), not
narrator inventions.
"""

from app.ai import context_builder
from app.core.enums import (
    CombatActorType,
    OrganizationOrigin,
    OrganizationType,
    OrganizationVisibility,
)
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.organizations.reputation import award_organization_reputation
from app.game.organizations.roles import create_role, join_organization
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Narrator Context")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def test_public_organization_headquartered_here_is_shown(db_session):
    campaign, region, village, character = _setup(db_session)
    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
        headquarters_location_id=village.id,
    )
    guildmaster = create_role(db_session, org, "Guildmaster", rank_order=0)
    from app.db.models.npc import NPC
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    join_organization(db_session, org, CombatActorType.NPC, osgar.id, role_id=guildmaster.id)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    org_section = context.split("KNOWN ORGANIZATIONS", 1)[1]
    assert "Guilda dos Caçadores de Cardal" in org_section
    assert "leader: Guildmaster" in org_section
    assert "membership: Not a member" in org_section


def test_secret_organization_elsewhere_is_never_shown(db_session):
    campaign, region, village, character = _setup(db_session)
    create_organization(
        db_session, campaign.id, "Culto Silencioso",
        organization_type=OrganizationType.CRIMINAL, origin=OrganizationOrigin.NATIVE,
        visibility=OrganizationVisibility.SECRET,
    )

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    org_section = context.split("KNOWN ORGANIZATIONS", 1)[1]
    assert "Culto Silencioso" not in org_section


def test_public_organization_headquartered_elsewhere_is_not_shown(db_session):
    campaign, region, village, character = _setup(db_session)
    from app.db.models.location import Location
    far_location = db_session.query(Location).filter(Location.id != village.id).first()
    create_organization(
        db_session, campaign.id, "Guilda Distante",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
        headquarters_location_id=far_location.id,
    )

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    org_section = context.split("KNOWN ORGANIZATIONS", 1)[1]
    assert "Guilda Distante" not in org_section


def test_membership_and_reputation_reflect_real_state(db_session):
    campaign, region, village, character = _setup(db_session)
    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
        headquarters_location_id=village.id,
    )
    hunter_role = create_role(db_session, org, "Caçador", rank_order=1)
    join_organization(db_session, org, CombatActorType.CHARACTER, character.id, role_id=hunter_role.id)
    award_organization_reputation(
        db_session, org, CombatActorType.CHARACTER, character.id,
        delta=15, reason="Completou um contrato de escolta.",
    )

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    org_section = context.split("KNOWN ORGANIZATIONS", 1)[1]
    assert "membership: Member (Caçador)" in org_section
    assert "reputation with this character: RELIABLE" in org_section


def test_no_known_organizations_shows_none(db_session):
    campaign, region, village, character = _setup(db_session)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    org_section = context.split("KNOWN ORGANIZATIONS", 1)[1]
    assert "- none" in org_section
