"""Phase 15R — World Simulation Integration.

Audit finding (no production code changed by this subphase): the layered
simulation architecture already built in Phase 7
(app.simulation.scope.build_simulation_scope, consumed by
app.simulation.npc_simulation/player_simulation) already scopes
individual-level ticking by real Character.location_id and established
NPC relationships — never by what the protagonist has *discovered*, and
never hardcoded to a single starting settlement. Organizations (Phase 13)
have no autonomous tick loop at all yet (by design, per that phase's own
scope) — they're acted on directly, which already works for any
organization regardless of distance from the protagonist. These tests
lock that in as regression protection now that the world is massive.
"""

from app.core.enums import CombatActorType, OrganizationActionType
from app.db.models.organization import Organization, OrganizationAction
from app.game.character.service import create_character
from app.game.organizations.actions import record_organization_action
from app.game.time.clock import advance_world_time
from app.game.world.seed import create_campaign, seed_initial_region
from app.simulation import world_simulation


def test_world_tick_runs_cleanly_across_a_massive_region(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)
    create_character(db_session, campaign.id, "Hero", region.id, village.id)

    # Several in-world days, in one jump — exercises arrival/group/player/
    # npc sub-ticks against a region with dozens of settlements/NPCs/orgs,
    # none of which the protagonist has been anywhere near.
    advance_world_time(db_session, campaign.id, 3 * 24 * 60)
    result = world_simulation.tick(db_session, campaign.id, 3 * 24 * 60)

    assert result is not None


def test_organization_action_can_be_recorded_for_a_never_visited_organization(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)
    create_character(db_session, campaign.id, "Hero", region.id, village.id)

    organization = db_session.query(Organization).filter(Organization.campaign_id == campaign.id).first()
    assert organization is not None
    # The protagonist has only ever been at the starting village — this
    # organization's headquarters is somewhere else entirely (Phase 15J).
    assert organization.headquarters_location_id != village.id

    action = record_organization_action(
        db_session, organization, OrganizationActionType.OTHER,
        "A organização toma uma decisão interna, longe de qualquer personagem jogável.",
        actor_type=CombatActorType.NPC,
        actor_id=organization.founder_id,
    )

    assert action.id is not None
    stored = (
        db_session.query(OrganizationAction)
        .filter(OrganizationAction.organization_id == organization.id)
        .one()
    )
    assert stored.id == action.id
