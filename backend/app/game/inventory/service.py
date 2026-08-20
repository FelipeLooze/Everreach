from sqlalchemy.orm import Session

from app.core.enums import ItemInstanceMode, ItemType
from app.db.models.item import InventoryItem, Item
from app.game.items.service import create_item_definition, item_key_from_name


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


def add_item(db: Session, character_id: str, item_name: str, quantity: int = 1) -> InventoryItem:
    item = get_or_create_item(db, item_name)
    entry = (
        db.query(InventoryItem)
        .filter(InventoryItem.character_id == character_id, InventoryItem.item_id == item.id)
        .first()
    )
    if entry:
        entry.quantity += quantity
    else:
        entry = InventoryItem(character_id=character_id, item_id=item.id, quantity=quantity)
        db.add(entry)
    db.flush()
    return entry


def list_inventory(db: Session, character_id: str) -> list[InventoryItem]:
    return db.query(InventoryItem).filter(InventoryItem.character_id == character_id).all()
