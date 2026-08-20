from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.character import Character
from app.services.event_log import log_event


def xp_to_next_level(level: int) -> float:
    """XP required to go from `level` to `level + 1`. Grows progressively — no fixed cap."""
    return round(50 * (level + 1) ** 1.5, 1)


def add_xp(character: Character, amount: float) -> int:
    """Add XP to a character, applying level-ups. Returns the number of levels gained."""
    if amount <= 0:
        return 0

    character.xp += amount
    levels_gained = 0

    while character.xp >= xp_to_next_level(character.level):
        character.xp -= xp_to_next_level(character.level)
        character.level += 1
        levels_gained += 1

    return levels_gained


def award_character_xp(
    db: Session,
    campaign_id: str,
    character: Character,
    amount: float,
) -> int:
    """
    Authoritatively award XP to a character.

    Applies XP and level changes and records the resulting
    structured events. Returns the number of levels gained.
    """

    if amount <= 0:
        return 0

    if character.campaign_id != campaign_id:
        raise ValueError(
            "Character does not belong to campaign."
        )

    previous_level = character.level

    levels_gained = add_xp(
        character,
        amount,
    )

    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.PLAYER_GAINED_XP,
        actor_type="character",
        actor_id=character.id,
        payload={
            "amount": amount,
            "current_xp": character.xp,
            "current_level": character.level,
        },
    )

    for new_level in range(
        previous_level + 1,
        character.level + 1,
    ):
        log_event(
            db,
            campaign_id,
            EventType.PLAYER_LEVELED_UP,
            actor_type="character",
            actor_id=character.id,
            payload={
                "previous_level": new_level - 1,
                "new_level": new_level,
            },
        )

    db.flush()

    return levels_gained


