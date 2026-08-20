from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    ItemInstanceMode,
    ItemLocationType,
    ItemOwnerType,
    ItemType,
)
from app.db.models.character import Character
from app.db.models.item import Item, ItemInstance
from app.game.items.service import (
    create_item_definition,
    create_item_instance,
    item_key_from_name,
    move_item_instance,
    set_item_owner,
)
from app.services.event_log import log_event


def get_or_create_item(db: Session, name: str, item_type: str = "misc", description: str = "") -> Item:
    normalized_type = item_type.strip().upper()
    try:
        definition_type = ItemType(normalized_type)
    except ValueError:
        definition_type = ItemType.MISC
    item = db.query(Item).filter(Item.name == name).first()
    if item:
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
    )


def add_item(db: Session, character_id: str, item_name: str, quantity: int = 1) -> ItemInstance:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("Item quantity must be a positive integer.")
    character = db.get(Character, character_id)
    if character is None:
        raise ValueError("Character does not exist.")
    item = get_or_create_item(db, item_name)
    entry = None
    if item.instance_mode == ItemInstanceMode.STACKABLE.value:
        entry = (
            db.query(ItemInstance)
            .filter(
                ItemInstance.definition_id == item.id,
                ItemInstance.location_type == ItemLocationType.CHARACTER.value,
                ItemInstance.location_ref == character_id,
            )
            .one_or_none()
        )
    if entry is None:
        entry = create_item_instance(db, item, quantity=quantity)
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
        },
    )
    return entry


def list_inventory(db: Session, character_id: str) -> list[ItemInstance]:
    return (
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
