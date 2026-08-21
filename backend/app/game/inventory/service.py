from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    ItemInstanceMode,
    ItemLocationType,
    ItemOwnerType,
    ItemQuality,
    ItemType,
)
from app.db.models.character import Character
from app.db.models.item import Item, ItemInstance
from app.game.items.materials import get_material_definition
from app.game.items.service import (
    create_item_definition,
    create_item_instance,
    item_key_from_name,
    move_item_instance,
    set_item_owner,
)
from app.services.event_log import log_event


def get_or_create_item(
    db: Session,
    name: str,
    item_type: str = "misc",
    description: str = "",
    base_weight: float | None = None,
) -> Item:
    normalized_type = item_type.strip().upper()
    try:
        definition_type = ItemType(normalized_type)
    except ValueError:
        definition_type = ItemType.MISC
    item = db.query(Item).filter(Item.name == name).first()
    if item:
        if base_weight is not None and item.base_weight != float(base_weight):
            raise ValueError("Item already exists with a different canonical weight.")
        return item
    instance_mode = (
        ItemInstanceMode.UNIQUE
        if definition_type in {
            ItemType.WEAPON,
            ItemType.ARMOR,
            ItemType.TOOL,
            ItemType.CONTAINER,
            ItemType.QUEST,
        }
        else ItemInstanceMode.STACKABLE
    )
    return create_item_definition(
        db,
        key=item_key_from_name(name),
        name=name,
        item_type=definition_type,
        instance_mode=instance_mode,
        description=description,
        base_weight=base_weight if base_weight is not None else 0.0,
    )


def add_item(
    db: Session,
    character_id: str,
    item_name: str,
    quantity: int = 1,
    *,
    base_weight: float | None = None,
    quality: ItemQuality = ItemQuality.STANDARD,
    material_key: str | None = None,
) -> ItemInstance:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("Item quantity must be a positive integer.")
    if not isinstance(quality, ItemQuality):
        raise ValueError("Invalid item quality.")
    character = db.get(Character, character_id)
    if character is None:
        raise ValueError("Character does not exist.")
    material = get_material_definition(db, material_key) if material_key else None
    if material_key and material is None:
        raise ValueError("Material definition does not exist.")
    item = get_or_create_item(db, item_name, base_weight=base_weight)
    entry = None
    if item.instance_mode == ItemInstanceMode.STACKABLE.value:
        entry = (
            db.query(ItemInstance)
            .filter(
                ItemInstance.definition_id == item.id,
                ItemInstance.location_type == ItemLocationType.CHARACTER.value,
                ItemInstance.location_ref == character_id,
                ItemInstance.quality == quality.value,
                ItemInstance.material_id == (material.id if material else None),
            )
            .one_or_none()
        )
    if entry is None:
        entry = create_item_instance(
            db,
            item,
            quantity=quantity,
            quality=quality,
            material=material,
        )
        move_item_instance(
            db,
            entry,
            location_type=ItemLocationType.CHARACTER,
            location_ref=character_id,
        )
        set_item_owner(
            db,
            entry,
            owner_type=ItemOwnerType.CHARACTER,
            owner_ref=character_id,
        )
    else:
        entry.quantity += quantity
        db.flush()
    log_event(
        db,
        character.campaign_id,
        EventType.PLAYER_GAINED_ITEM,
        actor_type="character",
        actor_id=character.id,
        payload={
            "item_instance_id": entry.id,
            "definition_id": item.id,
            "quantity": quantity,
            "quantity_after": entry.quantity,
            "quality": entry.quality,
            "material_key": material.key if material else None,
        },
    )
    return entry


def remove_item(db: Session, character_id: str, item_name: str, quantity: int = 1) -> None:
    """Phase 14F needs this to consume production inputs — Phase 10 had
    add_item's counterpart missing. Mirrors add_item's shape: character-
    held stacks only (matching add_item's own scope; NPC-held removal
    would need an NPC-side add_item counterpart that doesn't exist
    either — a pre-existing Phase 10 gap, not something this widens).
    Consumes from whichever matching stacks exist (any quality/material),
    oldest first, deleting a stack once it reaches zero. Raises if the
    character doesn't hold enough in total."""
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("Item quantity must be a positive integer.")
    item = db.query(Item).filter(Item.name == item_name).first()
    if item is None:
        raise ValueError(f"Item desconhecido: {item_name}")
    stacks = (
        db.query(ItemInstance)
        .filter(
            ItemInstance.definition_id == item.id,
            ItemInstance.location_type == ItemLocationType.CHARACTER.value,
            ItemInstance.location_ref == character_id,
        )
        .order_by(ItemInstance.id)
        .all()
    )
    available = sum(stack.quantity for stack in stacks)
    if available < quantity:
        raise ValueError(
            f"Quantidade insuficiente de '{item_name}' "
            f"({available} disponível, {quantity} necessário)."
        )
    remaining = quantity
    for stack in stacks:
        if remaining <= 0:
            break
        taken = min(stack.quantity, remaining)
        remaining -= taken
        if taken == stack.quantity:
            db.delete(stack)
        else:
            stack.quantity -= taken
    db.flush()


def list_inventory(db: Session, character_id: str) -> list[ItemInstance]:
    direct = (
        db.query(ItemInstance)
        .join(Item, Item.id == ItemInstance.definition_id)
        .filter(
            ItemInstance.location_type.in_(
                (
                    ItemLocationType.CHARACTER.value,
                    ItemLocationType.CHARACTER_EQUIPPED.value,
                )
            ),
            ItemInstance.location_ref == character_id,
        )
        .order_by(Item.name, ItemInstance.id)
        .all()
    )
    result = list(direct)
    pending = [entry.id for entry in direct]
    visited = set(pending)
    while pending:
        children = (
            db.query(ItemInstance)
            .filter(
                ItemInstance.location_type == ItemLocationType.CONTAINER.value,
                ItemInstance.location_ref.in_(pending),
            )
            .all()
        )
        pending = []
        for child in children:
            if child.id in visited:
                raise ValueError("Invalid recursive container hierarchy.")
            visited.add(child.id)
            result.append(child)
            pending.append(child.id)
    return sorted(result, key=lambda entry: (entry.definition.name, entry.id))
