from sqlalchemy.orm import Session

from app.db.models.location import Location
from app.db.models.region import Region
from app.db.models.simulated_player_arrival import (
    ScheduledSimulatedPlayerArrival,
)
from app.game.players import service as players_service
from app.game.time.clock import get_world_time
from app.simulation.results import (
    SimulatedPlayerArrivalSimulationResult,
)


def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> SimulatedPlayerArrivalSimulationResult:
    """
    Execute transported-person arrivals that are due.

    The world clock has already advanced before this function runs.
    Pending overdue arrivals are also caught up, but their canonical
    occurrence time remains their scheduled world minute.
    """

    if minutes <= 0:
        return SimulatedPlayerArrivalSimulationResult()

    current_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    due_arrivals = (
        db.query(ScheduledSimulatedPlayerArrival)
        .join(
            Location,
            ScheduledSimulatedPlayerArrival.location_id
            == Location.id,
        )
        .join(
            Region,
            Location.region_id == Region.id,
        )
        .filter(
            Region.campaign_id == campaign_id,
            ScheduledSimulatedPlayerArrival.executed_world_minute
            .is_(None),
            ScheduledSimulatedPlayerArrival.scheduled_world_minute
            <= current_world_minute,
        )
        .order_by(
            ScheduledSimulatedPlayerArrival.scheduled_world_minute,
            ScheduledSimulatedPlayerArrival.id,
        )
        .all()
    )

    executed = 0

    for arrival in due_arrivals:
        players_service.register_simulated_player_world_arrival(
            db,
            campaign_id,
            arrival.location_id,
            arrival.count,
            occurred_world_minute=(
                arrival.scheduled_world_minute
            ),
        )

        arrival.executed_world_minute = (
            arrival.scheduled_world_minute
        )

        executed += 1

    db.flush()

    return SimulatedPlayerArrivalSimulationResult(
        arrivals=executed,
    )