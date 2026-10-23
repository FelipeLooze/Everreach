"""Shared, measurable goals of transported guilds.

Every transported guild pursues one ACTIVE goal at a time, chosen by its
focus. Progress is never declared: it is counted from what the members
actually did since the goal was set — arrivals logged by travel
(PLAYER_MOVED / SIMULATED_PLAYER_MOVED) or the guild's own size. A met goal
becomes ACHIEVED and the next, bigger one replaces it.
"""

import json

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, EventType, GuildFocus, OrganizationGoalStatus
from app.db.models.event import WorldEvent
from app.db.models.location import Location
from app.db.models.organization import Organization, OrganizationGoal
from app.game.organizations.goals import active_goals, create_goal, set_goal_status

PLACES = "places"
WILD_TRIPS = "wild_trips"
SETTLEMENT_VISITS = "settlement_visits"
MEMBERS = "members"

WILD_LOCATION_TYPES = frozenset({
    "forest", "river", "road", "clearing", "ruins", "temple_ruins", "fort_ruins", "cave",
    "hills", "mountain_range", "plains", "marsh", "coast", "mine_entrance", "abandoned_mine",
    "tower",
})

# Per focus: the goal ladder. Growing to four comes first: it is reachable
# by any guild, including remote simulated ones that rarely travel. After
# the last step, the last metric keeps doubling.
_LADDERS = {
    GuildFocus.ADVENTURERS: ((MEMBERS, 4), (PLACES, 4), (MEMBERS, 6), (PLACES, 10)),
    GuildFocus.HUNTERS: ((MEMBERS, 4), (WILD_TRIPS, 6), (MEMBERS, 6), (WILD_TRIPS, 15)),
    GuildFocus.MERCHANTS: ((MEMBERS, 4), (SETTLEMENT_VISITS, 6), (MEMBERS, 6), (SETTLEMENT_VISITS, 15)),
    GuildFocus.RESEARCHERS: ((MEMBERS, 4), (PLACES, 5), (MEMBERS, 6), (PLACES, 12)),
    GuildFocus.BANDITS: ((MEMBERS, 4), (WILD_TRIPS, 8), (WILD_TRIPS, 16)),
}
_DESCRIPTIONS = {
    (GuildFocus.ADVENTURERS, PLACES): "Explorar juntos {target} lugares diferentes.",
    (GuildFocus.RESEARCHERS, PLACES): "Registrar {target} lugares diferentes nos cadernos da sociedade.",
    (GuildFocus.HUNTERS, WILD_TRIPS): "Fazer {target} incursões ao ermo.",
    (GuildFocus.BANDITS, WILD_TRIPS): "Dominar as estradas: {target} incursões fora dos povoados.",
    (GuildFocus.MERCHANTS, SETTLEMENT_VISITS): "Levar a guilda a {target} chegadas em povoados para negociar.",
    (GuildFocus.BANDITS, MEMBERS): "Juntar {target} membros no bando.",
}
_MEMBERS_DESCRIPTION = "Crescer até {target} membros."
_MOVE_EVENTS = (EventType.PLAYER_MOVED.value, EventType.SIMULATED_PLAYER_MOVED.value)
_ACTOR_TYPES = {
    CombatActorType.CHARACTER: "character",
    CombatActorType.SIMULATED_PLAYER: "simulated_player",
}


def _focus(organization: Organization) -> GuildFocus:
    return GuildFocus(organization.focus or GuildFocus.ADVENTURERS)


def _step(organization: Organization, index: int) -> tuple[str, int]:
    ladder = _LADDERS[_focus(organization)]
    if index < len(ladder):
        return ladder[index]
    metric, target = ladder[-1]
    return metric, target * 2 ** (index - len(ladder) + 1)


def _create_step(db: Session, organization: Organization, index: int) -> OrganizationGoal:
    metric, target = _step(organization, index)
    template = _DESCRIPTIONS.get((_focus(organization), metric), _MEMBERS_DESCRIPTION)
    goal = create_goal(db, organization, template.format(target=target), priority=index)
    goal.metric, goal.target, goal.progress = metric, target, 0
    db.flush()
    return goal


def current_goal(db: Session, organization: Organization) -> OrganizationGoal | None:
    return next((goal for goal in active_goals(db, organization.id) if goal.metric), None)


def achieved_count(db: Session, organization: Organization) -> int:
    return (
        db.query(OrganizationGoal)
        .filter(
            OrganizationGoal.organization_id == organization.id,
            OrganizationGoal.status == OrganizationGoalStatus.ACHIEVED,
            OrganizationGoal.metric.isnot(None),
        )
        .count()
    )


def ensure_goal(db: Session, organization: Organization) -> OrganizationGoal:
    return current_goal(db, organization) or _create_step(db, organization, achieved_count(db, organization))


def _arrivals(db: Session, organization: Organization, since: int) -> list[str]:
    """Destinations reached by members; members arriving together (same
    place, same hour) count as one trip."""
    from app.game.organizations.player_guilds import _active_members

    trips: set[tuple[str, int]] = set()
    for member in _active_members(db, organization):
        actor_type = _ACTOR_TYPES.get(member.member_type)
        if actor_type is None:
            continue
        events = db.query(WorldEvent.payload_json, WorldEvent.world_minute).filter(
            WorldEvent.campaign_id == organization.campaign_id,
            WorldEvent.event_type.in_(_MOVE_EVENTS),
            WorldEvent.actor_type == actor_type,
            WorldEvent.actor_id == member.member_id,
            WorldEvent.world_minute >= max(since, member.joined_world_minute),
        )
        for payload_json, world_minute in events:
            try:
                destination = json.loads(payload_json or "{}").get("to_location_id")
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue
            if destination:
                trips.add((destination, world_minute // 60))
    return [destination for destination, _hour in trips]


def measure(db: Session, organization: Organization, goal: OrganizationGoal) -> int:
    from app.game.organizations.player_guilds import _active_members

    if goal.metric == MEMBERS:
        return len(_active_members(db, organization))
    destinations = _arrivals(db, organization, goal.created_world_minute)
    if goal.metric == PLACES:
        return len(set(destinations))
    types = {
        location.id: location.type
        for location in db.query(Location).filter(Location.id.in_(set(destinations)))
    }
    wild = [destination for destination in destinations if types.get(destination) in WILD_LOCATION_TYPES]
    if goal.metric == WILD_TRIPS:
        return len(wild)
    return len(destinations) - len(wild)


def update_goal(db: Session, organization: Organization) -> OrganizationGoal | None:
    """Recount the current goal; returns the goal just ACHIEVED, if any."""
    goal = ensure_goal(db, organization)
    goal.progress = min(measure(db, organization, goal), goal.target or 0)
    if goal.target is None or goal.progress < goal.target:
        db.flush()
        return None
    set_goal_status(db, goal, OrganizationGoalStatus.ACHIEVED)
    _create_step(db, organization, achieved_count(db, organization))
    return goal
