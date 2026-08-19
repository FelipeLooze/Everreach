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


ACTION_CHANCE_PER_HOUR = 0.5
ACTION_INTERVAL_MINUTES = 60

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

    opportunity_world_minutes = boundary_minutes_crossed(
        end_world_minute,
        minutes,
        ACTION_INTERVAL_MINUTES,
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

    travel_started = 0
    moved = 0
    trained = 0

    for opportunity_world_minute in opportunity_world_minutes:
        for player in players:
            # Someone whose arrival happened before this opportunity
            # is already physically at the destination.

            if _complete_travel_if_due(
                db,
                campaign_id,
                player,
                opportunity_world_minute,
            ):
                moved += 1

            _sync_rest_activity(
                player,
                opportunity_world_minute,
            )

            # A person still in transit cannot perform a local activity.
            if _is_traveling(player):
                continue

            # Resting people do not roll for autonomous actions.
            if (
                player.activity
                == SimulatedPlayerActivity.RESTING.value
            ):
                continue

            if r.random() > ACTION_CHANCE_PER_HOUR:
                continue

            if (
                player.goal_type
                == SimulatedPlayerGoalType.TRAIN_SELF
            ):
                player.activity = (
                    SimulatedPlayerActivity.TRAINING.value
                )

                _train(
                    db,
                    campaign_id,
                    player,
                    opportunity_world_minute,
                )

                trained += 1
                continue

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
                    travel_started += 1

                continue

            if (
                player.goal_type
                == SimulatedPlayerGoalType.GATHER_KNOWLEDGE
            ):
                # There is no dedicated autonomous knowledge-gathering
                # action yet. Do not invent one or fall back to an
                # unrelated archetype action.
                continue

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
                    travel_started += 1

            elif (
                player.archetype
                == SimulatedPlayerArchetype.TRAINER
            ):
                player.activity = (
                    SimulatedPlayerActivity.TRAINING.value
                )

                _train(
                    db,
                    campaign_id,
                    player,
                    opportunity_world_minute,
                )
                trained += 1

            # SOCIAL does not choose an autonomous action in this MVP.

    # Arrival is independent from hourly action opportunities.
    # This matters for short ticks that cross no hour boundary.
    for player in players:
        if _complete_travel_if_due(
            db,
            campaign_id,
            player,
            end_world_minute,
        ):
            moved += 1

        _sync_rest_activity(
            player,
            end_world_minute,
        )
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

    completed_goal_type = player.goal_type
    completed_goal_subject = player.goal_subject
    completed_goal_description = player.goal

    player.goal_type = SimulatedPlayerGoalType.NONE
    player.goal_subject = None

    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_GOAL_COMPLETED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={
            "goal_type": completed_goal_type,
            "goal_subject": completed_goal_subject,
            "goal": completed_goal_description,
        },
        occurred_world_minute=world_minute,
    )

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

    if not connections:
        return False

    connection = _select_travel_connection(
        db,
        campaign_id,
        player,
        connections,
        r,
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