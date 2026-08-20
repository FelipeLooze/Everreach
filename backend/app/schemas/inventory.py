from pydantic import BaseModel

from app.core.enums import (
    BodyArea,
    EncumbranceTier,
    EquipmentSlot,
    ItemAccessibility,
    ItemQuality,
    PhysicalDamageProfile,
    ToolCapability,
    WeaponFamily,
    WeaponHandRequirement,
    WeaponReach,
)


class WeaponProfileResponse(BaseModel):
    family: WeaponFamily
    damage_profiles: list[PhysicalDamageProfile]
    reach: WeaponReach
    hand_requirement: WeaponHandRequirement


class ArmorProfileResponse(BaseModel):
    coverage: list[BodyArea]
    physical_protections: dict[PhysicalDamageProfile, int]


class ToolProfileResponse(BaseModel):
    capabilities: list[ToolCapability]


class InventoryItemResponse(BaseModel):
    item_instance_id: str
    item_id: str
    name: str
    type: str
    quantity: int
    quality: ItemQuality
    equipped: bool
    unit_weight: float
    total_weight: float
    equipped_slot: EquipmentSlot | None
    accessibility: ItemAccessibility
    allowed_slots: list[EquipmentSlot]
    weapon: WeaponProfileResponse | None
    armor: ArmorProfileResponse | None
    tool: ToolProfileResponse | None


class InventoryResponse(BaseModel):
    items: list[InventoryItemResponse]
    total_weight: float
    carrying_capacity: float
    load_ratio: float
    encumbrance: EncumbranceTier
