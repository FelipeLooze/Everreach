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
    select_known_simulated_player_for_reencounter,
)


def resolve_simulated_player_encounter(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    location_id: str,
    rng: random.Random | None = None,
    *,
    character_id: str | None = None,
) -> SimulatedPlayer | None:
    """
    Resolve one transported person for an encounter.

    When a character is known, previously met people who are genuinely
    present and available are preferred. Otherwise, another suitable
    persistent person may be selected.

    A new identity is materialized only when nobody suitable is already
    present and abstract population exists.
    """

    if character_id is not None:
        known = (
            select_known_simulated_player_for_reencounter(
                db,
                campaign_id,
                character_id,
                location_id,
                rng=rng,
            )
        )

        if known is not None:
            return known

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