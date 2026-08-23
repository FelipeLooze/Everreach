from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.character import Character
from app.db.models.defense import ItemArmorProfile
from app.db.models.equipment import ItemEquipmentProfile
from app.db.models.container import ItemContainerProfile
from app.db.models.item import Item, ItemInstance
from app.db.models.material import MaterialDefinition
from app.db.models.tool import ItemToolProfile
from app.db.models.weapon import ItemWeaponProfile
from app.game.inventory.service import list_inventory
from app.game.items.armor import get_armor_coverage, get_armor_physical_protections
from app.game.items.encumbrance import get_character_encumbrance
from app.game.items.durability import get_item_condition
from app.game.items.containers import get_container_content_weight
from app.game.items.equipment import (
    get_allowed_equipment_slots,
    resolve_item_accessibility,
)
from app.game.items.materials import material_weight_factor
from app.game.items.tools import get_tool_capabilities
from app.game.items.weapons import get_weapon_damage_profiles
from app.game.visual.item import build_item_visual_spec
from app.schemas.inventory import (
    ArmorProfileResponse,
    ContainerProfileResponse,
    InventoryItemResponse,
    InventoryResponse,
    MaterialResponse,
    ToolProfileResponse,
    WeaponProfileResponse,
)

router = APIRouter(prefix="/api/campaigns", tags=["inventory"])


@router.get("/{campaign_id}/inventory", response_model=InventoryResponse)
def get_inventory(campaign_id: str, character_id: str, db: Session = Depends(get_db)):
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha")

    entries = list_inventory(db, character_id)
    items = []
    for entry in entries:
        item = db.get(Item, entry.definition_id)
        if item is None:
            continue
        equipment_profile = db.get(ItemEquipmentProfile, item.id)
        weapon_profile = db.get(ItemWeaponProfile, item.id)
        armor_profile = db.get(ItemArmorProfile, item.id)
        tool_profile = db.get(ItemToolProfile, item.id)
        container_profile = db.get(ItemContainerProfile, item.id)
        parent = (
            db.get(ItemInstance, entry.location_ref)
            if entry.location_type == "CONTAINER" and entry.location_ref
            else None
        )
        parent_definition = (
            db.get(Item, parent.definition_id) if parent is not None else None
        )
        material = (
            db.get(MaterialDefinition, entry.material_id)
            if entry.material_id is not None
            else None
        )
        unit_weight = item.base_weight * material_weight_factor(material)
        items.append(
            InventoryItemResponse(
                item_instance_id=entry.id,
                item_id=item.id,
                name=item.name,
                type=item.type,
                quantity=entry.quantity,
                quality=entry.quality,
                condition=get_item_condition(entry),
                material=(
                    MaterialResponse(key=material.key, name=material.name)
                    if material is not None
                    else None
                ),
                container=(
                    ContainerProfileResponse(
                        weight_capacity=container_profile.weight_capacity,
                        content_weight=round(
                            get_container_content_weight(db, entry), 3
                        ),
                    )
                    if container_profile is not None
                    else None
                ),
                contained_in_item_instance_id=(parent.id if parent else None),
                contained_in_name=(parent_definition.name if parent_definition else None),
                equipped=entry.equipped,
                unit_weight=round(unit_weight, 3),
                total_weight=round(unit_weight * entry.quantity, 3),
                equipped_slot=entry.equipped_slot,
                accessibility=resolve_item_accessibility(db, entry),
                allowed_slots=(
                    sorted(
                        get_allowed_equipment_slots(equipment_profile),
                        key=lambda slot: slot.value,
                    )
                    if equipment_profile is not None
                    else []
                ),
                weapon=(
                    WeaponProfileResponse(
                        family=weapon_profile.weapon_family,
                        damage_profiles=sorted(
                            get_weapon_damage_profiles(weapon_profile),
                            key=lambda profile: profile.value,
                        ),
                        reach=weapon_profile.reach,
                        hand_requirement=weapon_profile.hand_requirement,
                    )
                    if weapon_profile is not None
                    else None
                ),
                armor=(
                    ArmorProfileResponse(
                        coverage=sorted(
                            get_armor_coverage(armor_profile), key=lambda area: area.value
                        ),
                        physical_protections=get_armor_physical_protections(armor_profile),
                    )
                    if armor_profile is not None
                    else None
                ),
                tool=(
                    ToolProfileResponse(
                        capabilities=sorted(
                            get_tool_capabilities(tool_profile),
                            key=lambda capability: capability.value,
                        )
                    )
                    if tool_profile is not None
                    else None
                ),
                signature_ornamentation=build_item_visual_spec(db, entry.id).signature_ornamentation,
            )
        )
    encumbrance = get_character_encumbrance(db, character_id)
    return InventoryResponse(
        items=items,
        total_weight=encumbrance.total_weight,
        carrying_capacity=encumbrance.carrying_capacity,
        load_ratio=encumbrance.load_ratio,
        encumbrance=encumbrance.tier,
    )
