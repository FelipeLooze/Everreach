from pydantic import BaseModel

from app.core.enums import EncumbranceTier


class InventoryItemResponse(BaseModel):
    item_id: str
    name: str
    type: str
    quantity: int
    equipped: bool
    unit_weight: float
    total_weight: float


class InventoryResponse(BaseModel):
    items: list[InventoryItemResponse]
    total_weight: float
    carrying_capacity: float
    load_ratio: float
    encumbrance: EncumbranceTier
