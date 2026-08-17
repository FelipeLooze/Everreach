from pydantic import BaseModel


class InventoryItemResponse(BaseModel):
    item_id: str
    name: str
    type: str
    quantity: int
    equipped: bool


class InventoryResponse(BaseModel):
    items: list[InventoryItemResponse]
