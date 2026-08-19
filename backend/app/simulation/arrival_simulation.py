import hashlib
import random
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

def _arrival_rng(
    campaign_id: str,
    base_world_minute: int,
) -> random.Random:
    """
    Build a deterministic RNG for one canonical arrival step.

    Arrival randomness must not consume the RNG used by other world
    simulations and must not depend on tick partitioning.
    """

    seed_material = (
        f"{campaign_id}:"
        f"{base_world_minute}:"
        "simulated-player-arrival"
    )

    digest = hashlib.sha256(
        seed_material.encode("utf-8")
    ).digest()

    seed = int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=False,
    )

    return random.Random(seed)

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

    tick_start_world_minute = (
        current_world_minute - minutes
    )

    players_service.ensure_automatic_simulated_player_world_arrival_scheduled(
        db,
        campaign_id,
        rng=_arrival_rng(
            campaign_id,
            tick_start_world_minute,
        ),
        base_world_minute=tick_start_world_minute,
    )

    executed = 0

    while True:
        arrival = (
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
            .first()
        )

        if arrival is None:
            break

        canonical_world_minute = (
            arrival.scheduled_world_minute
        )

        players_service.register_simulated_player_world_arrival(
            db,
            campaign_id,
            arrival.location_id,
            arrival.count,
            occurred_world_minute=canonical_world_minute,
        )

        arrival.executed_world_minute = (
            canonical_world_minute
        )

        db.flush()

        executed += 1

        players_service.ensure_automatic_simulated_player_world_arrival_scheduled(
            db,
            campaign_id,
            rng=_arrival_rng(
                campaign_id,
                canonical_world_minute,
            ),
            base_world_minute=canonical_world_minute,
        )

    db.flush()

    return SimulatedPlayerArrivalSimulationResult(
        arrivals=executed,
    )