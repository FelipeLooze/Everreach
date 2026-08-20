from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    CharacterStatus,
    EarthProfession,
    EventType,
)
from app.db.models.character import Character, CharacterAttribute
from app.services.event_log import log_event
from app.game.professions.backgrounds import affinity_for_earth_profession
from app.game.professions.service import get_or_create_profession
from app.game.attributes.service import ensure_attribute_catalog

DEFAULT_ATTRIBUTES = {
    CharacterAttributeKey.STRENGTH: 10,
    CharacterAttributeKey.AGILITY: 10,
    CharacterAttributeKey.VITALITY: 10,
    CharacterAttributeKey.INTELLIGENCE: 10,
    CharacterAttributeKey.WISDOM: 10,
    CharacterAttributeKey.ENDURANCE: 10,
}


def create_character(
    db: Session,
    campaign_id: str,
    name: str,
    region_id: str | None = None,
    location_id: str | None = None,
    *,
    earth_profession: EarthProfession | None = None,
) -> Character:
    ensure_attribute_catalog(db)
    affinity = affinity_for_earth_profession(earth_profession)
    if affinity is not None:
        get_or_create_profession(
            db,
            affinity.profession_key,
            affinity.profession_name,
        )
    character = Character(
        campaign_id=campaign_id,
        name=name,
        background=(affinity.background_label if affinity else None),
        profession_affinity_key=(
            affinity.profession_key if affinity else None
        ),
        level=0,
        xp=0,
        hp_current=20,
        hp_max=20,
        mana_current=10,
        mana_max=10,
        stamina_current=20,
        stamina_max=20,
        status=CharacterStatus.ALIVE,
        region_id=region_id,
        location_id=location_id,
    )
    db.add(character)
    db.flush()

    for attr_key, value in DEFAULT_ATTRIBUTES.items():
        db.add(
            CharacterAttribute(
                character_id=character.id,
                key=attr_key.value,
                value=value,
                development=0.0,
            )
        )

    log_event(
        db,
        campaign_id,
        EventType.CHARACTER_CREATED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "name": name,
            "background": character.background,
            "profession_affinity_key": character.profession_affinity_key,
        },
    )

    db.flush()
    return character


def kill_character(db: Session, campaign_id: str, character: Character, cause: str = "") -> None:
    """Death is permanent — there is no respawn. See spec section 57."""
    character.status = CharacterStatus.DEAD
    log_event(
        db,
        campaign_id,
        EventType.PLAYER_DIED,
        actor_type="character",
        actor_id=character.id,
        payload={"cause": cause},
    )
