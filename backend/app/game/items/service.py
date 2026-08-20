import re
import unicodedata

from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    ItemInstanceMode,
    ItemLocationType,
    ItemOwnerType,
    ItemType,
)
from app.db.models.character import Character
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.region import Region
from app.services.event_log import log_event


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


def move_item_instance(
    db: Session,
    instance: ItemInstance,
    *,
    location_type: ItemLocationType,
    location_ref: str | None,
) -> ItemInstance:
    if db.get(ItemInstance, instance.id) is None:
        raise ItemFoundationError("Item instance must be persisted first.")
    if not isinstance(location_type, ItemLocationType):
        raise ItemFoundationError("Invalid item location type.")
    normalized_ref = location_ref.strip() if location_ref else None
    target_campaign = _location_campaign(
        db,
        instance,
        location_type,
        normalized_ref,
    )
    _bind_campaign(instance, target_campaign)
    before = {
        "type": instance.location_type,
        "ref": instance.location_ref,
    }
    if before == {"type": location_type.value, "ref": normalized_ref}:
        return instance
    instance.location_type = location_type.value
    instance.location_ref = normalized_ref
    db.flush()
    if instance.campaign_id is not None:
        log_event(
            db,
            instance.campaign_id,
            EventType.ITEM_LOCATION_CHANGED,
            actor_type="item_instance",
            actor_id=instance.id,
            payload={
                "definition_id": instance.definition_id,
                "before": before,
                "after": {"type": location_type.value, "ref": normalized_ref},
            },
        )
    return instance


def set_item_owner(
    db: Session,
    instance: ItemInstance,
    *,
    owner_type: ItemOwnerType,
    owner_ref: str | None,
) -> ItemInstance:
    if db.get(ItemInstance, instance.id) is None:
        raise ItemFoundationError("Item instance must be persisted first.")
    if not isinstance(owner_type, ItemOwnerType):
        raise ItemFoundationError("Invalid item owner type.")
    normalized_ref = owner_ref.strip() if owner_ref else None
    owner_campaign = _owner_campaign(db, owner_type, normalized_ref)
    _bind_campaign(instance, owner_campaign)
    before = {"type": instance.owner_type, "ref": instance.owner_ref}
    if before == {"type": owner_type.value, "ref": normalized_ref}:
        return instance
    instance.owner_type = owner_type.value
    instance.owner_ref = normalized_ref
    db.flush()
    if instance.campaign_id is not None:
        log_event(
            db,
            instance.campaign_id,
            EventType.ITEM_OWNERSHIP_CHANGED,
            actor_type="item_instance",
            actor_id=instance.id,
            payload={
                "definition_id": instance.definition_id,
                "before": before,
                "after": {"type": owner_type.value, "ref": normalized_ref},
            },
        )
    return instance


def _location_campaign(
    db: Session,
    instance: ItemInstance,
    location_type: ItemLocationType,
    location_ref: str | None,
) -> str | None:
    if location_type == ItemLocationType.UNPLACED:
        if location_ref is not None:
            raise ItemFoundationError("Unplaced items cannot have a location reference.")
        return instance.campaign_id
    if not location_ref:
        raise ItemFoundationError("Placed items require a location reference.")
    if location_type in {
        ItemLocationType.CHARACTER,
        ItemLocationType.CHARACTER_EQUIPPED,
    }:
        character = db.get(Character, location_ref)
        if character is None:
            raise ItemFoundationError("Item location character does not exist.")
        return character.campaign_id
    if location_type == ItemLocationType.NPC:
        npc = db.get(NPC, location_ref)
        if npc is None:
            raise ItemFoundationError("Item location NPC does not exist.")
        return npc.campaign_id
    if location_type == ItemLocationType.WORLD_LOCATION:
        location = db.get(Location, location_ref)
        region = db.get(Region, location.region_id) if location is not None else None
        if region is None:
            raise ItemFoundationError("World item location does not exist.")
        return region.campaign_id
    if location_type == ItemLocationType.CONTAINER:
        raise ItemFoundationError(
            "Container placement remains unavailable until container-cycle "
            "validation is implemented in Phase 10K."
        )
    raise ItemFoundationError("Unsupported item location type.")


def _owner_campaign(
    db: Session,
    owner_type: ItemOwnerType,
    owner_ref: str | None,
) -> str | None:
    if owner_type == ItemOwnerType.NONE:
        if owner_ref is not None:
            raise ItemFoundationError("Unowned items cannot have an owner reference.")
        return None
    if not owner_ref:
        raise ItemFoundationError("Owned items require an owner reference.")
    if owner_type == ItemOwnerType.CHARACTER:
        character = db.get(Character, owner_ref)
        if character is None:
            raise ItemFoundationError("Item owner character does not exist.")
        return character.campaign_id
    if owner_type == ItemOwnerType.NPC:
        npc = db.get(NPC, owner_ref)
        if npc is None:
            raise ItemFoundationError("Item owner NPC does not exist.")
        return npc.campaign_id
    raise ItemFoundationError("Unsupported item owner type.")


def _bind_campaign(instance: ItemInstance, campaign_id: str | None) -> None:
    if campaign_id is None:
        return
    if instance.campaign_id is None:
        instance.campaign_id = campaign_id
    elif instance.campaign_id != campaign_id:
        raise ItemFoundationError("Item cannot move between campaigns.")
