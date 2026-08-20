from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models.character import Character
from app.game.attributes.service import list_character_attributes
from app.game.classes.service import get_active_class, list_visible_class_offers
from app.game.professions.service import list_character_professions
from app.game.progression.service import xp_to_next_level


@dataclass(frozen=True)
class SystemProgressionContext:
    character: Character
    xp_to_next_level: float
    attributes: tuple
    professions: tuple
    active_class: object | None
    class_offers: tuple


def build_system_progression_context(
    db: Session,
    campaign_id: str,
    character_id: str,
) -> SystemProgressionContext:
    """Build only information the protagonist's System is allowed to reveal."""
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    return SystemProgressionContext(
        character=character,
        xp_to_next_level=xp_to_next_level(character.level),
        attributes=tuple(list_character_attributes(db, character.id)),
        professions=tuple(list_character_professions(db, character.id)),
        active_class=get_active_class(db, character),
        class_offers=tuple(list_visible_class_offers(db, character.id)),
    )
