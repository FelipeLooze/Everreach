import random

from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService
from app.db.models.simulated_player import SimulatedPlayer
from app.game.players.generator import (
    materialize_simulated_player,
)
from app.game.players.service import (
    abstract_simulated_player_count_at_location,
    select_existing_simulated_player_for_encounter,
)


def resolve_simulated_player_encounter(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    location_id: str,
    rng: random.Random | None = None,
) -> SimulatedPlayer | None:
    """
    Resolve one transported person for an encounter.

    Existing persistent people who are physically present are always
    preferred. A new identity is materialized only when nobody suitable
    is already present and abstract population exists.
    """

    existing = (
        select_existing_simulated_player_for_encounter(
            db,
            campaign_id,
            location_id,
            rng=rng,
        )
    )

    if existing is not None:
        return existing

    available_population = (
        abstract_simulated_player_count_at_location(
            db,
            campaign_id,
            location_id,
        )
    )

    if available_population <= 0:
        return None

    return materialize_simulated_player(
        db,
        llm_service,
        campaign_id,
        location_id,
    )