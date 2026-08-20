from pydantic import BaseModel

from app.core.enums import EncumbranceTier, EquipmentSlot, ItemAccessibility


class InventoryItemResponse(BaseModel):
    item_instance_id: str
    item_id: str
    name: str
    type: str
    quantity: int
    equipped: bool
    unit_weight: float
    total_weight: float
    equipped_slot: EquipmentSlot | None
    accessibility: ItemAccessibility
    allowed_slots: list[EquipmentSlot]


class InventoryResponse(BaseModel):
    items: list[InventoryItemResponse]
    total_weight: float
    carrying_capacity: float
    load_ratio: float
    encumbrance: EncumbranceTier
