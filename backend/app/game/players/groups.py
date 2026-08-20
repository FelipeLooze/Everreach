from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    SimulatedPlayerGroupStatus,
    SimulatedPlayerStatus,
)
from app.db.models.location import LocationConnection
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.simulated_player_group import (
    SimulatedPlayerGroup,
    SimulatedPlayerGroupMember,
)
from app.game.time.clock import get_world_time
from app.game.travel.service import calculate_travel_minutes
from app.services.event_log import log_event


def active_group_for_player(
    db: Session,
    player_id: str,
) -> SimulatedPlayerGroup | None:
    return (
        db.query(SimulatedPlayerGroup)
        .join(
            SimulatedPlayerGroupMember,
            SimulatedPlayerGroupMember.group_id == SimulatedPlayerGroup.id,
        )
        .filter(
            SimulatedPlayerGroupMember.simulated_player_id == player_id,
            SimulatedPlayerGroupMember.active.is_(True),
            SimulatedPlayerGroup.status == SimulatedPlayerGroupStatus.ACTIVE.value,
        )
        .first()
    )


def active_group_members(
    db: Session,
    group_id: str,
) -> list[SimulatedPlayer]:
    return (
        db.query(SimulatedPlayer)
        .join(
            SimulatedPlayerGroupMember,
            SimulatedPlayerGroupMember.simulated_player_id == SimulatedPlayer.id,
        )
        .filter(
            SimulatedPlayerGroupMember.group_id == group_id,
            SimulatedPlayerGroupMember.active.is_(True),
            SimulatedPlayer.status == SimulatedPlayerStatus.ACTIVE.value,
        )
        .order_by(SimulatedPlayer.id)
        .all()
    )


def create_group(
    db: Session,
    campaign_id: str,
    leader: SimulatedPlayer,
    members: list[SimulatedPlayer],
    *,
    goal: str,
    occurred_world_minute: int | None = None,
) -> SimulatedPlayerGroup:
    unique = {member.id: member for member in [leader, *members]}
    people = list(unique.values())
    if len(people) < 2:
        raise ValueError("A group requires at least two active members.")
    if any(
        person.campaign_id != campaign_id
        or person.status != SimulatedPlayerStatus.ACTIVE.value
        or person.location_id != leader.location_id
        or person.travel_arrival_world_minute is not None
        or active_group_for_player(db, person.id) is not None
        for person in people
    ):
        raise ValueError("Group members must be active, available and co-located.")

    world_minute = (
        occurred_world_minute
        if occurred_world_minute is not None
        else get_world_time(db, campaign_id).total_minutes()
    )
    group = SimulatedPlayerGroup(
        campaign_id=campaign_id,
        leader_id=leader.id,
        location_id=leader.location_id,
        goal=goal,
        status=SimulatedPlayerGroupStatus.ACTIVE.value,
        created_world_minute=world_minute,
    )
    db.add(group)
    db.flush()
    for person in people:
        db.add(
            SimulatedPlayerGroupMember(
                group_id=group.id,
                simulated_player_id=person.id,
                joined_world_minute=world_minute,
                active=True,
            )
        )
    db.flush()
    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_GROUP_CREATED,
        actor_type="simulated_player_group",
        actor_id=group.id,
        payload={
            "leader_id": leader.id,
            "member_ids": sorted(unique),
            "location_id": leader.location_id,
            "goal": goal,
        },
        occurred_world_minute=world_minute,
    )
    for person in people:
        log_event(
            db,
            campaign_id,
            EventType.SIMULATED_PLAYER_GROUP_JOINED,
            actor_type="simulated_player",
            actor_id=person.id,
            payload={"group_id": group.id},
            occurred_world_minute=world_minute,
        )
    return group


def join_group(
    db: Session,
    group: SimulatedPlayerGroup,
    player: SimulatedPlayer,
    *,
    occurred_world_minute: int | None = None,
) -> SimulatedPlayerGroupMember:
    world_minute = (
        occurred_world_minute
        if occurred_world_minute is not None
        else get_world_time(db, group.campaign_id).total_minutes()
    )
    if (
        group.status != SimulatedPlayerGroupStatus.ACTIVE.value
        or player.campaign_id != group.campaign_id
        or player.status != SimulatedPlayerStatus.ACTIVE.value
        or player.location_id != group.location_id
        or player.travel_arrival_world_minute is not None
        or active_group_for_player(db, player.id) is not None
    ):
        raise ValueError("Player cannot join this group in the current state.")
    membership = (
        db.query(SimulatedPlayerGroupMember)
        .filter(
            SimulatedPlayerGroupMember.group_id == group.id,
            SimulatedPlayerGroupMember.simulated_player_id == player.id,
        )
        .first()
    )
    if membership is None:
        membership = SimulatedPlayerGroupMember(
            group_id=group.id,
            simulated_player_id=player.id,
            joined_world_minute=world_minute,
            active=True,
        )
        db.add(membership)
    else:
        membership.active = True
        membership.joined_world_minute = world_minute
        membership.left_world_minute = None
    db.flush()
    log_event(
        db,
        group.campaign_id,
        EventType.SIMULATED_PLAYER_GROUP_JOINED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={"group_id": group.id},
        occurred_world_minute=world_minute,
    )
    return membership


def leave_group(
    db: Session,
    player_id: str,
    *,
    occurred_world_minute: int,
) -> None:
    group = active_group_for_player(db, player_id)
    if group is None:
        return
    membership = (
        db.query(SimulatedPlayerGroupMember)
        .filter(
            SimulatedPlayerGroupMember.group_id == group.id,
            SimulatedPlayerGroupMember.simulated_player_id == player_id,
            SimulatedPlayerGroupMember.active.is_(True),
        )
        .one()
    )
    membership.active = False
    membership.left_world_minute = occurred_world_minute
    db.flush()
    remaining = active_group_members(db, group.id)
    log_event(
        db,
        group.campaign_id,
        EventType.SIMULATED_PLAYER_GROUP_LEFT,
        actor_type="simulated_player",
        actor_id=player_id,
        payload={"group_id": group.id},
        occurred_world_minute=occurred_world_minute,
    )
    if len(remaining) < 2:
        group.status = SimulatedPlayerGroupStatus.DISSOLVED.value
        for row in (
            db.query(SimulatedPlayerGroupMember)
            .filter(
                SimulatedPlayerGroupMember.group_id == group.id,
                SimulatedPlayerGroupMember.active.is_(True),
            )
            .all()
        ):
            row.active = False
            row.left_world_minute = occurred_world_minute
        log_event(
            db,
            group.campaign_id,
            EventType.SIMULATED_PLAYER_GROUP_DISSOLVED,
            actor_type="simulated_player_group",
            actor_id=group.id,
            payload={},
            occurred_world_minute=occurred_world_minute,
        )
    elif group.leader_id == player_id:
        group.leader_id = remaining[0].id
    db.flush()


def start_group_travel(
    db: Session,
    group: SimulatedPlayerGroup,
    connection: LocationConnection,
    *,
    occurred_world_minute: int,
) -> bool:
    members = active_group_members(db, group.id)
    if (
        group.status != SimulatedPlayerGroupStatus.ACTIVE.value
        or len(members) < 2
        or connection.from_location_id != group.location_id
        or not connection.active
        or any(
            member.location_id != group.location_id
            or member.travel_arrival_world_minute is not None
            for member in members
        )
    ):
        return False

    travel_minutes = calculate_travel_minutes(connection)
    arrival = occurred_world_minute + travel_minutes
    for member in members:
        member.travel_connection_id = connection.id
        member.travel_destination_id = connection.to_location_id
        member.travel_started_world_minute = occurred_world_minute
        member.travel_arrival_world_minute = arrival
        member.activity_until_world_minute = None
        log_event(
            db,
            group.campaign_id,
            EventType.SIMULATED_PLAYER_TRAVEL_STARTED,
            actor_type="simulated_player",
            actor_id=member.id,
            payload={
                "group_id": group.id,
                "connection_id": connection.id,
                "from_location_id": connection.from_location_id,
                "to_location_id": connection.to_location_id,
                "travel_minutes": travel_minutes,
                "arrival_world_minute": arrival,
            },
            occurred_world_minute=occurred_world_minute,
        )
    log_event(
        db,
        group.campaign_id,
        EventType.SIMULATED_PLAYER_GROUP_TRAVEL_STARTED,
        actor_type="simulated_player_group",
        actor_id=group.id,
        payload={
            "connection_id": connection.id,
            "from_location_id": connection.from_location_id,
            "to_location_id": connection.to_location_id,
            "member_ids": [member.id for member in members],
        },
        occurred_world_minute=occurred_world_minute,
    )
    db.flush()
    return True


def synchronize_group_location(db: Session, player_id: str) -> None:
    group = active_group_for_player(db, player_id)
    if group is None:
        return
    members = active_group_members(db, group.id)
    if members and all(
        member.travel_arrival_world_minute is None
        and member.location_id == members[0].location_id
        for member in members
    ):
        group.location_id = members[0].location_id
