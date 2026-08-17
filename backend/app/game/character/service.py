from sqlalchemy.orm import Session

from app.core.enums import CharacterStatus, EventType
from app.db.models.character import Character, CharacterAttribute
from app.services.event_log import log_event

DEFAULT_ATTRIBUTES = {
    "Força": 10,
    "Agilidade": 10,
    "Vitalidade": 10,
    "Inteligência": 10,
    "Sabedoria": 10,
    "Resistência": 10,
}


def create_character(
    db: Session,
    campaign_id: str,
    name: str,
    region_id: str | None = None,
    location_id: str | None = None,
) -> Character:
    character = Character(
        campaign_id=campaign_id,
        name=name,
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

    for attr_name, value in DEFAULT_ATTRIBUTES.items():
        db.add(CharacterAttribute(character_id=character.id, name=attr_name, value=value))

    log_event(
        db,
        campaign_id,
        EventType.CHARACTER_CREATED,
        actor_type="character",
        actor_id=character.id,
        payload={"name": name},
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
