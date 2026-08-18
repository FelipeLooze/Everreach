import random

from sqlalchemy.orm import Session
from app.game.time.clock import get_world_time
from app.core.enums import EventType, SimulatedPlayerArchetype, SimulatedPlayerStatus
from app.db.models.location import LocationConnection
from app.db.models.simulated_player import SimulatedPlayer
from app.services.event_log import log_event
from app.simulation.results import PlayerSimulationResult

ACTION_CHANCE_PER_HOUR = 0.5

def _hour_boundaries_crossed(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> int:
    if minutes <= 0:
        return 0

    end_total = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    start_total = end_total - minutes

    return max(
        0,
        (end_total // 60) - (start_total // 60),
    )

def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
    rng: random.Random | None = None,
) -> PlayerSimulationResult:
    """Advance simulated transported people on absolute hourly opportunities.

    The number of opportunities depends on world-clock boundaries crossed,
    not on how the protagonist divided the elapsed time into actions.
    """
    if minutes <= 0:
        return PlayerSimulationResult()

    opportunities = _hour_boundaries_crossed(
        db,
        campaign_id,
        minutes,
    )

    if opportunities <= 0:
        return PlayerSimulationResult()

    moved = 0
    trained = 0

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

    for _ in range(opportunities):
        for player in players:
            if r.random() > ACTION_CHANCE_PER_HOUR:
                continue

            if player.archetype in (
                SimulatedPlayerArchetype.EXPLORER,
                SimulatedPlayerArchetype.ADVENTURER,
            ):
                if _try_move(
                    db,
                    campaign_id,
                    player,
                    r,
                ):
                    moved += 1

            elif (
                player.archetype
                == SimulatedPlayerArchetype.TRAINER
            ):
                _train(
                    db,
                    campaign_id,
                    player,
                )
                trained += 1
            # SOCIAL permanece parado no MVP.
    return PlayerSimulationResult(
        moved=moved,
        trained=trained,
    )


def _try_move(db: Session, campaign_id: str, player: SimulatedPlayer, r: random.Random) -> None:
    connections = (
        db.query(LocationConnection)
        .filter(LocationConnection.from_location_id == player.location_id, LocationConnection.active.is_(True))
        .all()
    )
    if not connections:
        return False

    destination = r.choice(connections).to_location_id
    player.location_id = destination

    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_MOVED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={"to_location_id": destination},
    )
    return True


def _train(db: Session, campaign_id: str, player: SimulatedPlayer) -> None:
    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_TRAINED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={},
    )
