import random

from sqlalchemy.orm import Session

from app.core.enums import EventType, SimulatedPlayerArchetype, SimulatedPlayerStatus
from app.db.models.location import LocationConnection
from app.db.models.simulated_player import SimulatedPlayer
from app.services.event_log import log_event

ACTION_CHANCE_PER_HOUR = 0.5


def tick(db: Session, campaign_id: str, minutes: int, rng: random.Random | None = None) -> None:
    """Rule-based world advancement for simulated players (spec section 52).
    Not an AI — a simple state machine per archetype. Simulated players keep
    existing/acting even when the protagonist is elsewhere."""
    if minutes <= 0:
        return

    r = rng or random.Random()
    chance = min(1.0, ACTION_CHANCE_PER_HOUR * (minutes / 60))

    players = (
        db.query(SimulatedPlayer)
        .filter(SimulatedPlayer.campaign_id == campaign_id, SimulatedPlayer.status == SimulatedPlayerStatus.ACTIVE)
        .all()
    )

    for player in players:
        if r.random() > chance:
            continue

        if player.archetype in (SimulatedPlayerArchetype.EXPLORER, SimulatedPlayerArchetype.ADVENTURER):
            _try_move(db, campaign_id, player, r)
        elif player.archetype == SimulatedPlayerArchetype.TRAINER:
            _train(db, campaign_id, player)
        # SOCIAL archetype stays put in the MVP — no social simulation yet.


def _try_move(db: Session, campaign_id: str, player: SimulatedPlayer, r: random.Random) -> None:
    connections = (
        db.query(LocationConnection)
        .filter(LocationConnection.from_location_id == player.location_id, LocationConnection.active.is_(True))
        .all()
    )
    if not connections:
        return

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


def _train(db: Session, campaign_id: str, player: SimulatedPlayer) -> None:
    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_TRAINED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={},
    )
