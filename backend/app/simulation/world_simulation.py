import random

from sqlalchemy.orm import Session

from app.simulation import npc_simulation, player_simulation


def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
    rng: random.Random | None = None,
) -> None:
    """Advance autonomous world systems after the world clock moves forward."""

    if minutes <= 0:
        return

    player_simulation.tick(
        db,
        campaign_id,
        minutes,
        rng=rng,
    )

    npc_simulation.tick(
        db,
        campaign_id,
        minutes,
    )