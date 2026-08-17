import random

from sqlalchemy.orm import Session

from app.simulation import npc_simulation, player_simulation


def tick(db: Session, campaign_id: str, minutes: int, rng: random.Random | None = None) -> None:
    """Advance the parts of the world that don't depend on the protagonist.
    Called after the world clock advances (see game/time/clock.py + game/engine.py)."""
    player_simulation.tick(db, campaign_id, minutes, rng=rng)
    npc_simulation.tick(db, campaign_id, minutes)
