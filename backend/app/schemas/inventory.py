from pydantic import BaseModel

from app.core.enums import (
    BodyArea,
    EncumbranceTier,
    EquipmentSlot,
    ItemAccessibility,
    ItemCondition,
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


class MaterialResponse(BaseModel):
    key: str
    name: str


class ContainerProfileResponse(BaseModel):
    weight_capacity: float
    content_weight: float


class InventoryItemResponse(BaseModel):
    item_instance_id: str
    item_id: str
    name: str
    type: str
    quantity: int
    quality: ItemQuality
    condition: ItemCondition | None
    material: MaterialResponse | None
    container: ContainerProfileResponse | None
    contained_in_item_instance_id: str | None
    contained_in_name: str | None
    equipped: bool
    unit_weight: float
    total_weight: float
    equipped_slot: EquipmentSlot | None
    accessibility: ItemAccessibility
    allowed_slots: list[EquipmentSlot]
    weapon: WeaponProfileResponse | None
    armor: ArmorProfileResponse | None
    tool: ToolProfileResponse | None
    # Phase 21O — the one piece of app.game.visual.item.ItemVisualSpec
    # not already covered by the fields above (material/quality/
    # condition/weapon family were all real Phase 10 Canon already
    # exposed here). None for the overwhelming majority of ordinary
    # items — see app.game.visual.item's own docstring.
    signature_ornamentation: str | None = None
    # Phase 21Q — opaque reference to a FUTURE ITEM_ILLUSTRATION asset;
    # None until a later generation phase sets one. The frontend must
    # render a placeholder whenever this is None (fallback-first).
    asset_ref: str | None = None


class InventoryResponse(BaseModel):
    items: list[InventoryItemResponse]
    total_weight: float
    carrying_capacity: float
    load_ratio: float
    encumbrance: EncumbranceTier
