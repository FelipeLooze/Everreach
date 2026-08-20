import re
import unicodedata

from sqlalchemy.orm import Session

from app.core.enums import ItemInstanceMode, ItemType
from app.db.models.item import ItemDefinition, ItemInstance


class ItemFoundationError(ValueError):
    pass


def item_key_from_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name.casefold())
    ascii_name = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    key = re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")
    if not key:
        raise ItemFoundationError("Item name must contain letters or numbers.")
    return key


def create_item_definition(
    db: Session,
    *,
    key: str,
    name: str,
    item_type: ItemType,
    instance_mode: ItemInstanceMode,
    description: str = "",
) -> ItemDefinition:
    normalized_key = key.strip().lower()
    normalized_name = name.strip()
    normalized_description = description.strip()
    if not re.fullmatch(r"[a-z0-9_]+", normalized_key):
        raise ItemFoundationError(
            "Item definition key must use lowercase letters, numbers and underscores."
        )
    if not normalized_name:
        raise ItemFoundationError("Item definition name is required.")
    if not isinstance(item_type, ItemType):
        raise ItemFoundationError("Invalid item type.")
    if not isinstance(instance_mode, ItemInstanceMode):
        raise ItemFoundationError("Invalid item instance mode.")

    existing = (
        db.query(ItemDefinition)
        .filter(ItemDefinition.key == normalized_key)
        .one_or_none()
    )
    values = {
        "name": normalized_name,
        "type": item_type.value,
        "instance_mode": instance_mode.value,
        "description": normalized_description,
    }
    if existing is not None:
        if any(getattr(existing, field) != value for field, value in values.items()):
            raise ItemFoundationError(
                "Item definition already exists with different canonical data."
            )
        return existing

    definition = ItemDefinition(key=normalized_key, **values)
    db.add(definition)
    db.flush()
    return definition


def create_item_instance(
    db: Session,
    definition: ItemDefinition,
    *,
    quantity: int = 1,
) -> ItemInstance:
    if db.get(ItemDefinition, definition.id) is None:
        raise ItemFoundationError("Item definition must be persisted first.")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ItemFoundationError("Item instance quantity must be a positive integer.")
    try:
        mode = ItemInstanceMode(definition.instance_mode)
    except ValueError as exc:
        raise ItemFoundationError("Persisted item instance mode is invalid.") from exc
    if mode == ItemInstanceMode.UNIQUE and quantity != 1:
        raise ItemFoundationError("Unique item instances must have quantity 1.")

    instance = ItemInstance(definition_id=definition.id, quantity=quantity)
    db.add(instance)
    db.flush()
    return instance


def get_item_definition(db: Session, key: str) -> ItemDefinition | None:
    return (
        db.query(ItemDefinition)
        .filter(ItemDefinition.key == key.strip().lower())
        .one_or_none()
    )
