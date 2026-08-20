from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.character import Character
from app.db.models.equipment import ItemEquipmentProfile
from app.db.models.item import Item
from app.db.models.weapon import ItemWeaponProfile
from app.game.inventory.service import list_inventory
from app.game.items.encumbrance import get_character_encumbrance
from app.game.items.equipment import get_allowed_equipment_slots, item_accessibility
from app.game.items.weapons import get_weapon_damage_profiles
from app.schemas.inventory import (
    InventoryItemResponse,
    InventoryResponse,
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
        items.append(
            InventoryItemResponse(
                item_instance_id=entry.id,
                item_id=item.id,
                name=item.name,
                type=item.type,
                quantity=entry.quantity,
                equipped=entry.equipped,
                unit_weight=item.base_weight,
                total_weight=round(item.base_weight * entry.quantity, 3),
                equipped_slot=entry.equipped_slot,
                accessibility=item_accessibility(entry),
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
