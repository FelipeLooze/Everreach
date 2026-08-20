import json

from sqlalchemy.orm import Session

from app.core.enums import CharacterXPSource, EventType
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.services.event_log import log_event


def xp_to_next_level(level: int) -> float:
    """XP required to go from `level` to `level + 1`. Grows progressively — no fixed cap."""
    return float(round(25 * (level + 1) ** 1.7))


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
    *,
    source: CharacterXPSource,
    experience_key: str,
) -> int:
    """
    Authoritatively award XP to a character.

    Applies XP and level changes for one backend-approved significant
    experience and records the resulting structured events. Reusing the
    same experience key for the same character is idempotent.
    """

    if amount <= 0:
        return 0

    if character.campaign_id != campaign_id:
        raise ValueError(
            "Character does not belong to campaign."
        )

    if not isinstance(source, CharacterXPSource):
        raise ValueError("Invalid Character XP source.")

    normalized_experience_key = experience_key.strip()
    if not normalized_experience_key:
        raise ValueError("Character XP requires an experience key.")

    previous_awards = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.event_type == EventType.PLAYER_GAINED_XP.value,
            WorldEvent.actor_type == "character",
            WorldEvent.actor_id == character.id,
        )
        .all()
    )
    for event in previous_awards:
        try:
            payload = json.loads(event.payload_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if payload.get("experience_key") == normalized_experience_key:
            return 0

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
            "source": source.value,
            "experience_key": normalized_experience_key,
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
