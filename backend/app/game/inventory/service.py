from sqlalchemy.orm import Session

from app.db.models.item import InventoryItem, Item


def get_or_create_item(db: Session, name: str, item_type: str = "misc", description: str = "") -> Item:
    item = db.query(Item).filter(Item.name == name).first()
    if item:
        return item
    item = Item(name=name, type=item_type, description=description)
    db.add(item)
    db.flush()
    return item


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
