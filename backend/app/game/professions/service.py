import re
from math import isfinite

from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.character import Character
from app.db.models.profession import CharacterProfession, Profession
from app.services.event_log import log_event


MINIMUM_INITIAL_PROFESSION_XP = 0.1
PROFESSION_XP_PER_LEVEL = 10.0
BACKGROUND_AFFINITY_MULTIPLIER = 1.10
_PROFESSION_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def profession_xp_to_next_level(_level: int) -> float:
    """Foundation curve, isolated here so later balancing does not alter persistence."""
    return PROFESSION_XP_PER_LEVEL


def get_or_create_profession(
    db: Session,
    key: str,
    name: str,
    *,
    description: str = "",
) -> Profession:
    normalized_key = key.strip().upper()
    normalized_name = name.strip()
    if not _PROFESSION_KEY_PATTERN.fullmatch(normalized_key):
        raise ValueError("Invalid profession key.")
    if not normalized_name:
        raise ValueError("Profession name is required.")

    profession = (
        db.query(Profession)
        .filter(Profession.key == normalized_key)
        .first()
    )
    if profession is not None:
        return profession

    profession = Profession(
        key=normalized_key,
        name=normalized_name,
        description=description.strip(),
    )
    db.add(profession)
    db.flush()
    return profession


def add_profession_xp(
    character_profession: CharacterProfession,
    amount: float,
) -> int:
    if not isfinite(amount):
        raise ValueError("Profession XP amount must be finite.")
    if amount <= 0:
        return 0

    character_profession.xp += amount
    levels_gained = 0
    while character_profession.xp >= profession_xp_to_next_level(
        character_profession.level
    ):
        character_profession.xp -= profession_xp_to_next_level(
            character_profession.level
        )
        character_profession.level += 1
        levels_gained += 1
    return levels_gained


def award_profession_xp(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    profession_key: str,
    profession_name: str,
    amount: float,
    profession_description: str = "",
) -> CharacterProfession | None:
    """Award Profession XP without granting Character XP or creating zero-XP rows."""
    if not isfinite(amount):
        raise ValueError("Profession XP amount must be finite.")
    if amount <= 0:
        return None
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")

    normalized_key = profession_key.strip().upper()
    has_background_affinity = (
        character.profession_affinity_key == normalized_key
    )
    effective_amount = (
        amount * BACKGROUND_AFFINITY_MULTIPLIER
        if has_background_affinity
        else amount
    )
    profession = (
        db.query(Profession)
        .filter(Profession.key == normalized_key)
        .first()
    )
    character_profession = None
    if profession is not None:
        character_profession = (
            db.query(CharacterProfession)
            .filter(
                CharacterProfession.character_id == character.id,
                CharacterProfession.profession_id == profession.id,
            )
            .first()
        )

    if (
        character_profession is None
        and effective_amount < MINIMUM_INITIAL_PROFESSION_XP
    ):
        return None

    if profession is None:
        profession = get_or_create_profession(
            db,
            normalized_key,
            profession_name,
            description=profession_description,
        )

    created = character_profession is None
    if character_profession is None:
        character_profession = CharacterProfession(
            character_id=character.id,
            profession_id=profession.id,
            level=0,
            xp=0.0,
        )
        db.add(character_profession)
        db.flush()

    previous_level = character_profession.level
    levels_gained = add_profession_xp(
        character_profession,
        effective_amount,
    )
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.PLAYER_GAINED_PROFESSION_XP,
        actor_type="character",
        actor_id=character.id,
        payload={
            "profession_id": profession.id,
            "profession_key": profession.key,
            "profession_name": profession.name,
            "base_amount": amount,
            "affinity_multiplier": (
                BACKGROUND_AFFINITY_MULTIPLIER
                if has_background_affinity
                else 1.0
            ),
            "amount": effective_amount,
            "created": created,
            "current_xp": character_profession.xp,
            "current_level": character_profession.level,
        },
    )
    for new_level in range(previous_level + 1, previous_level + levels_gained + 1):
        log_event(
            db,
            campaign_id,
            EventType.PLAYER_PROFESSION_LEVELED_UP,
            actor_type="character",
            actor_id=character.id,
            payload={
                "profession_id": profession.id,
                "profession_key": profession.key,
                "profession_name": profession.name,
                "previous_level": new_level - 1,
                "new_level": new_level,
            },
        )
    db.flush()
    return character_profession


def list_character_professions(
    db: Session,
    character_id: str,
) -> list[CharacterProfession]:
    return (
        db.query(CharacterProfession)
        .join(Profession)
        .filter(CharacterProfession.character_id == character_id)
        .order_by(Profession.name.asc())
        .all()
    )
