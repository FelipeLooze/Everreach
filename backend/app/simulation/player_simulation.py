import random
import json

from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    KnowledgeCertainty,
    KnowerType,
    SimulatedPlayerActivity,
    SimulatedPlayerArchetype,
    SimulatedPlayerStatus,
    SimulatedPlayerGoalType,
)
from app.db.models.knowledge import (
    KnowledgeFact,
    KnowledgeKnower,
)
from app.db.models.location import Location, LocationConnection
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.simulated_player_routine import (
    SimulatedPlayerRoutine,
)
from app.db.models.event import WorldEvent
from app.game.time.clock import (
    HOURS_PER_DAY,
    MINUTES_PER_HOUR,
    get_world_time,
)
from app.game.travel.service import calculate_travel_minutes
from app.services.event_log import log_event
from app.simulation.cadence import boundary_minutes_crossed
from app.simulation.results import PlayerSimulationResult
from app.simulation.scope import (
    SimulationScope,
    SimulationTier,
    build_simulation_scope,
)
from app.game.players.goals import complete_goal
from app.game.players.groups import (
    active_group_for_player,
    start_group_travel,
    synchronize_group_location,
)
from app.game.players.knowledge import gather_local_knowledge
from app.game.players.progression import apply_training
from app.game.players.risk import acceptable_connections


ACTION_CHANCE_PER_HOUR = 0.5
ACTION_INTERVAL_MINUTES = 60
RELEVANT_ACTION_INTERVAL_MINUTES = 6 * 60
MINUTES_PER_DAY = HOURS_PER_DAY * MINUTES_PER_HOUR


def _hour_boundaries_crossed(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> int:
    """Return how many absolute hourly boundaries were crossed.

    Kept as a small compatibility helper for callers/tests that only need
    the count. Travel simulation itself uses the exact boundary minutes.
    """
    if minutes <= 0:
        return 0

    end_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    return len(
        boundary_minutes_crossed(
            end_world_minute,
            minutes,
            ACTION_INTERVAL_MINUTES,
        )
    )

def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
    rng: random.Random | None = None,
    scope: SimulationScope | None = None,
) -> PlayerSimulationResult:
    """Advance autonomous transported people.

    Travel uses absolute world minutes. A transported person begins travel
    during an hourly action opportunity and changes physical location only
    when the route's travel time has actually elapsed.
    """
    if minutes <= 0:
        return PlayerSimulationResult()

    end_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    detailed_opportunity_world_minutes = boundary_minutes_crossed(
        end_world_minute,
        minutes,
        ACTION_INTERVAL_MINUTES,
    )

    relevant_opportunity_world_minutes = boundary_minutes_crossed(
        end_world_minute,
        minutes,
        RELEVANT_ACTION_INTERVAL_MINUTES,
    )

    r = rng or random.Random()

    players = (
        db.query(SimulatedPlayer)
        .filter(
            SimulatedPlayer.campaign_id == campaign_id,
            SimulatedPlayer.status
            == SimulatedPlayerStatus.ACTIVE,
        )
        .order_by(SimulatedPlayer.id)
        .all()
    )

    active_scope = scope or build_simulation_scope(
        db,
        campaign_id,
    )

    detailed_players = [
        player
        for player in players
        if active_scope.simulated_player_tier(player.location_id)
        == SimulationTier.DETAILED
    ]
    relevant_players = [
        player
        for player in players
        if active_scope.simulated_player_tier(player.location_id)
        == SimulationTier.RELEVANT
    ]

    travel_started = 0
    moved = 0
    trained = 0

    schedules = (
        (
            detailed_players,
            detailed_opportunity_world_minutes,
            ACTION_CHANCE_PER_HOUR,
        ),
        (
            relevant_players,
            relevant_opportunity_world_minutes,
            _aggregated_action_chance(
                RELEVANT_ACTION_INTERVAL_MINUTES
            ),
        ),
    )

    for tier_players, opportunity_minutes, action_chance in schedules:
        for opportunity_world_minute in opportunity_minutes:
            for player in tier_players:
                result = _process_player_opportunity(
                    db,
                    campaign_id,
                    player,
                    opportunity_world_minute,
                    r,
                    action_chance,
                )
                travel_started += result.travel_started
                moved += result.moved
                trained += result.trained

    # Arrival and local state expiry are independent from action cadence.
    for player in players:
        if _complete_travel_if_due(
            db,
            campaign_id,
            player,
            end_world_minute,
        ):
            moved += 1

        _sync_temporary_activity(player, end_world_minute)
        _sync_established_routine(db, player, end_world_minute)
        _sync_rest_activity(player, end_world_minute)

    return PlayerSimulationResult(
        travel_started=travel_started,
        moved=moved,
        trained=trained,
    )


def _aggregated_action_chance(interval_minutes: int) -> float:
    """Equivalent chance of at least one action over an aggregate interval."""
    intervals = interval_minutes / ACTION_INTERVAL_MINUTES
    return 1 - (1 - ACTION_CHANCE_PER_HOUR) ** intervals


def _process_player_opportunity(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    opportunity_world_minute: int,
    r: random.Random,
    action_chance: float,
) -> PlayerSimulationResult:
    moved = 0
    trained = 0
    travel_started = 0

    # Someone whose arrival happened before this opportunity is already
    # physically at the destination.
    if _complete_travel_if_due(
        db,
        campaign_id,
        player,
        opportunity_world_minute,
    ):
        moved = 1

    _sync_temporary_activity(player, opportunity_world_minute)
    _sync_established_routine(db, player, opportunity_world_minute)
    _sync_rest_activity(player, opportunity_world_minute)

    if _is_traveling(player):
        return PlayerSimulationResult(moved=moved)

    if player.activity == SimulatedPlayerActivity.RESTING.value:
        return PlayerSimulationResult(moved=moved)

    if _temporary_activity_is_active(player, opportunity_world_minute):
        if player.activity == SimulatedPlayerActivity.TRAINING.value:
            _train(db, campaign_id, player, opportunity_world_minute)
            trained = 1

        return PlayerSimulationResult(moved=moved, trained=trained)

    if r.random() > action_chance:
        return PlayerSimulationResult(moved=moved)

    if player.goal_type == SimulatedPlayerGoalType.TRAIN_SELF:
        player.activity = SimulatedPlayerActivity.TRAINING.value
        _train(db, campaign_id, player, opportunity_world_minute)
        return PlayerSimulationResult(moved=moved, trained=1)

    if player.goal_type in (
        SimulatedPlayerGoalType.EXPLORE_REGION,
        SimulatedPlayerGoalType.SEEK_DANGER,
    ):
        if _try_start_travel(
            db,
            campaign_id,
            player,
            r,
            opportunity_world_minute,
        ):
            travel_started = 1

        return PlayerSimulationResult(
            travel_started=travel_started,
            moved=moved,
        )

    if player.goal_type == SimulatedPlayerGoalType.GATHER_KNOWLEDGE:
        if gather_local_knowledge(db, player):
            complete_goal(
                db,
                player,
                occurred_world_minute=opportunity_world_minute,
            )
        return PlayerSimulationResult(moved=moved)

    if player.archetype in (
        SimulatedPlayerArchetype.EXPLORER,
        SimulatedPlayerArchetype.ADVENTURER,
    ):
        if _try_start_travel(
            db,
            campaign_id,
            player,
            r,
            opportunity_world_minute,
        ):
            travel_started = 1
    elif player.archetype == SimulatedPlayerArchetype.TRAINER:
        player.activity = SimulatedPlayerActivity.TRAINING.value
        _train(db, campaign_id, player, opportunity_world_minute)
        trained = 1

    # SOCIAL does not choose an autonomous action in this MVP.
    return PlayerSimulationResult(
        travel_started=travel_started,
        moved=moved,
        trained=trained,
    )


def _is_traveling(
    player: SimulatedPlayer,
) -> bool:
    return (
        player.travel_arrival_world_minute
        is not None
    )


def _temporary_activity_is_active(
    player: SimulatedPlayer,
    world_minute: int,
) -> bool:
    if (
        player.activity_until_world_minute
        is None
    ):
        return False

    if (
        world_minute
        >= player.activity_until_world_minute
    ):
        return False

    return player.activity in (
        SimulatedPlayerActivity.TRAINING.value,
        SimulatedPlayerActivity.SOCIALIZING.value,
        SimulatedPlayerActivity.WORKING.value,
    )


def _sync_temporary_activity(
    player: SimulatedPlayer,
    world_minute: int,
) -> None:
    """
    Finish a temporary local activity when its canonical end minute
    has been reached.

    Travel is handled separately and takes precedence over local
    activities.
    """

    if _is_traveling(player):
        return

    if (
        player.activity_until_world_minute
        is None
    ):
        return

    if (
        world_minute
        < player.activity_until_world_minute
    ):
        return

    player.activity_until_world_minute = None

    if player.activity in (
        SimulatedPlayerActivity.TRAINING.value,
        SimulatedPlayerActivity.SOCIALIZING.value,
        SimulatedPlayerActivity.WORKING.value,
    ):
        player.activity = (
            SimulatedPlayerActivity.AVAILABLE.value
        )


def _sync_established_routine(
    db: Session,
    player: SimulatedPlayer,
    world_minute: int,
) -> None:
    """
    Activate the established daily routine that applies at this
    canonical world minute.

    An already-running temporary activity has precedence. Established
    routines only apply while the person is physically at the routine's
    configured location.
    """

    if _is_traveling(player):
        return

    if _temporary_activity_is_active(
        player,
        world_minute,
    ):
        return

    minute_of_day = (
        world_minute % MINUTES_PER_DAY
    )

    routine = (
        db.query(SimulatedPlayerRoutine)
        .filter(
            SimulatedPlayerRoutine.simulated_player_id
            == player.id,
            SimulatedPlayerRoutine.location_id
            == player.location_id,
            SimulatedPlayerRoutine.enabled.is_(True),
            SimulatedPlayerRoutine.established_world_minute
            <= world_minute,
            SimulatedPlayerRoutine.start_minute_of_day
            <= minute_of_day,
            SimulatedPlayerRoutine.end_minute_of_day
            > minute_of_day,
        )
        .order_by(
            SimulatedPlayerRoutine.start_minute_of_day,
            SimulatedPlayerRoutine.id,
        )
        .first()
    )

    if routine is None:
        return

    start_of_day_world_minute = (
        world_minute - minute_of_day
    )

    routine_end_world_minute = (
        start_of_day_world_minute
        + routine.end_minute_of_day
    )

    player.activity = routine.activity
    player.activity_until_world_minute = (
        routine_end_world_minute
    )


def _sync_rest_activity(
    player: SimulatedPlayer,
    world_minute: int,
) -> None:
    """
    Synchronize the local resting state for one transported person.

    Travel is a separate physical state and takes precedence over local
    activity. Daytime only clears RESTING; it does not overwrite other
    activity states.
    """

    if _is_traveling(player):
        return

    hour = (
        world_minute // MINUTES_PER_HOUR
    ) % HOURS_PER_DAY

    if hour >= 22 or hour < 6:
        player.activity_until_world_minute = None

        player.activity = (
            SimulatedPlayerActivity.RESTING.value
        )
        return

    if (
        player.activity
        == SimulatedPlayerActivity.RESTING.value
    ):
        player.activity = (
            SimulatedPlayerActivity.AVAILABLE.value
        )

def _known_outgoing_connections(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
) -> list[LocationConnection]:
    """Return active outgoing routes this transported person can navigate.

    RUMOR alone is not enough to use a route autonomously.
    BELIEVED and CONFIRMED route knowledge are navigable.
    """
    rows = (
        db.query(KnowledgeFact.subject)
        .join(
            KnowledgeKnower,
            KnowledgeKnower.fact_id
            == KnowledgeFact.id,
        )
        .filter(
            KnowledgeFact.campaign_id
            == campaign_id,
            KnowledgeFact.subject.like(
                "connection:%"
            ),
            KnowledgeKnower.knower_type
            == KnowerType.SIMULATED_PLAYER.value,
            KnowledgeKnower.knower_id
            == player.id,
            KnowledgeKnower.certainty.in_(
                (
                    KnowledgeCertainty.BELIEVED.value,
                    KnowledgeCertainty.CONFIRMED.value,
                )
            ),
        )
        .all()
    )

    known_connection_ids = {
        subject.removeprefix("connection:")
        for (subject,) in rows
    }

    if not known_connection_ids:
        return []

    return (
        db.query(LocationConnection)
        .filter(
            LocationConnection.id.in_(
                known_connection_ids
            ),
            LocationConnection.from_location_id
            == player.location_id,
            LocationConnection.active.is_(True),
        )
        .order_by(LocationConnection.id)
        .all()
    )

def _visited_location_ids(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
) -> set[str]:
    """Return locations this transported person has physically visited."""

    visited = {
        player.location_id,
    }

    events = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign_id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_MOVED.value,
            WorldEvent.actor_type
            == "simulated_player",
            WorldEvent.actor_id
            == player.id,
        )
        .order_by(
            WorldEvent.world_minute,
            WorldEvent.id,
        )
        .all()
    )

    for event in events:
        try:
            payload = json.loads(
                event.payload_json or "{}"
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            continue

        from_location_id = payload.get(
            "from_location_id"
        )
        to_location_id = payload.get(
            "to_location_id"
        )

        if from_location_id:
            visited.add(from_location_id)

        if to_location_id:
            visited.add(to_location_id)

    return visited

def _explore_region_goal_is_complete(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    region_id: str,
) -> bool:
    region_location_ids = {
        location_id
        for (location_id,) in (
            db.query(Location.id)
            .filter(
                Location.region_id == region_id,
            )
            .all()
        )
    }

    if not region_location_ids:
        return False

    visited_location_ids = _visited_location_ids(
        db,
        campaign_id,
        player,
    )

    return region_location_ids.issubset(
        visited_location_ids
    )

def _complete_goal_if_satisfied(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    world_minute: int,
) -> bool:
    if (
        player.goal_type
        == SimulatedPlayerGoalType.NONE
    ):
        return False

    if (
        player.goal_type
        == SimulatedPlayerGoalType.EXPLORE_REGION
    ):
        region_id = _goal_region_id(
            player
        )

        if not region_id:
            return False

        if not _explore_region_goal_is_complete(
            db,
            campaign_id,
            player,
            region_id,
        ):
            return False

    else:
        return False

    complete_goal(db, player, occurred_world_minute=world_minute)

    return True

def _goal_region_id(
    player: SimulatedPlayer,
) -> str | None:
    if (
        player.goal_type
        != SimulatedPlayerGoalType.EXPLORE_REGION
    ):
        return None

    if not player.goal_subject:
        return None

    prefix = "region:"

    if not player.goal_subject.startswith(prefix):
        return None

    region_id = player.goal_subject[len(prefix):]

    return region_id or None


def _unvisited_connections_in_region(
    db: Session,
    connections: list[LocationConnection],
    visited_location_ids: set[str],
    region_id: str,
) -> list[LocationConnection]:
    destination_ids = {
        connection.to_location_id
        for connection in connections
        if connection.to_location_id
        not in visited_location_ids
    }

    if not destination_ids:
        return []

    locations = (
        db.query(Location)
        .filter(
            Location.id.in_(destination_ids),
            Location.region_id == region_id,
        )
        .all()
    )

    location_ids_in_region = {
        location.id
        for location in locations
    }

    return [
        connection
        for connection in connections
        if connection.to_location_id
        in location_ids_in_region
    ]

def _select_travel_connection(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    connections: list[LocationConnection],
    r: random.Random,
) -> LocationConnection:
    """Choose a known route according to goal first, then archetype."""

    visited_locations: set[str] | None = None

    if (
        player.goal_type
        == SimulatedPlayerGoalType.EXPLORE_REGION
    ):
        target_region_id = _goal_region_id(
            player
        )

        if target_region_id:
            visited_locations = (
                _visited_location_ids(
                    db,
                    campaign_id,
                    player,
                )
            )

            goal_connections = (
                _unvisited_connections_in_region(
                    db,
                    connections,
                    visited_locations,
                    target_region_id,
                )
            )

            if goal_connections:
                return r.choice(
                    goal_connections
                )

    if (
        player.goal_type
        == SimulatedPlayerGoalType.SEEK_DANGER
    ):
        highest_danger = max(
            connection.danger
            for connection in connections
        )

        dangerous_connections = [
            connection
            for connection in connections
            if connection.danger
            == highest_danger
        ]

        return r.choice(
            dangerous_connections
        )

    if (
        player.archetype
        == SimulatedPlayerArchetype.EXPLORER
    ):
        if visited_locations is None:
            visited_locations = (
                _visited_location_ids(
                    db,
                    campaign_id,
                    player,
                )
            )

        unexplored_connections = [
            connection
            for connection in connections
            if connection.to_location_id
            not in visited_locations
        ]

        if unexplored_connections:
            return r.choice(
                unexplored_connections
            )

    if (
        player.archetype
        == SimulatedPlayerArchetype.ADVENTURER
    ):
        highest_danger = max(
            connection.danger
            for connection in connections
        )

        dangerous_connections = [
            connection
            for connection in connections
            if connection.danger
            == highest_danger
        ]

        return r.choice(
            dangerous_connections
        )

    return r.choice(connections)

def _try_start_travel(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    r: random.Random,
    opportunity_world_minute: int,
) -> bool:
    connections = _known_outgoing_connections(
        db,
        campaign_id,
        player,
    )
    connections = acceptable_connections(player, connections)

    if not connections:
        return False

    group = active_group_for_player(db, player.id) if db is not None else None
    if group is not None and group.leader_id != player.id:
        return False

    connection = _select_travel_connection(
        db,
        campaign_id,
        player,
        connections,
        r,
    )

    if group is not None:
        return start_group_travel(
            db,
            group,
            connection,
            occurred_world_minute=opportunity_world_minute,
        )

    travel_minutes = calculate_travel_minutes(
        connection
    )

    arrival_world_minute = (
        opportunity_world_minute
        + travel_minutes
    )

    player.activity = (
        SimulatedPlayerActivity.AVAILABLE.value
    )
    player.activity_until_world_minute = None

    player.travel_connection_id = connection.id

    player.travel_destination_id = (
        connection.to_location_id
    )
    player.travel_started_world_minute = (
        opportunity_world_minute
    )
    player.travel_arrival_world_minute = (
        arrival_world_minute
    )

    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_TRAVEL_STARTED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={
            "connection_id": connection.id,
            "from_location_id": (
                connection.from_location_id
            ),
            "to_location_id": (
                connection.to_location_id
            ),
            "travel_minutes": travel_minutes,
            "arrival_world_minute": (
                arrival_world_minute
            ),
        },
        occurred_world_minute=(
            opportunity_world_minute
        ),
    )

    return True


def _complete_travel_if_due(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    current_world_minute: int,
) -> bool:
    arrival_world_minute = (
        player.travel_arrival_world_minute
    )

    if arrival_world_minute is None:
        return False

    if arrival_world_minute > current_world_minute:
        return False

    destination_id = (
        player.travel_destination_id
    )

    if destination_id is None:
        return False

    origin_id = player.location_id
    connection_id = (
        player.travel_connection_id
    )
    connection = db.get(LocationConnection, connection_id) if connection_id else None

    player.location_id = destination_id

    player.travel_connection_id = None
    player.travel_destination_id = None
    player.travel_started_world_minute = None
    player.travel_arrival_world_minute = None

    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_MOVED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={
            "connection_id": connection_id,
            "from_location_id": origin_id,
            "to_location_id": destination_id,
        },
        occurred_world_minute=(
            arrival_world_minute
        ),
    )

    _complete_goal_if_satisfied(
        db,
        campaign_id,
        player,
        arrival_world_minute,
    )

    if (
        player.goal_type == SimulatedPlayerGoalType.SEEK_DANGER.value
        and connection is not None
    ):
        required_danger = 3
        if player.goal_subject and player.goal_subject.startswith("danger:"):
            try:
                required_danger = int(player.goal_subject.removeprefix("danger:"))
            except ValueError:
                pass
        if connection.danger >= required_danger:
            complete_goal(db, player, occurred_world_minute=arrival_world_minute)

    synchronize_group_location(db, player.id)

    return True


def _train(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    opportunity_world_minute: int,
) -> None:
    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_TRAINED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={},
        occurred_world_minute=(
            opportunity_world_minute
        ),
    )
    target_level = player.level + 1
    if (
        player.goal_type == SimulatedPlayerGoalType.TRAIN_SELF.value
        and player.goal_subject
        and player.goal_subject.startswith("level:")
    ):
        try:
            target_level = int(player.goal_subject.removeprefix("level:"))
        except ValueError:
            pass
    apply_training(
        db,
        campaign_id,
        player,
        occurred_world_minute=opportunity_world_minute,
    )
    if (
        player.goal_type == SimulatedPlayerGoalType.TRAIN_SELF.value
        and player.level >= target_level
    ):
        complete_goal(db, player, occurred_world_minute=opportunity_world_minute)
