"""Phase 21D — Item Visual Identity.

build_item_visual_spec is a READ-ONLY derivation, not a new store of
truth: item_type, weapon_family, material and quality are already real
Phase 10 Canon (app.db.models.item/weapon/material); condition is
already computed by app.game.items.durability.get_item_condition. None
of that is duplicated into app.game.visual.spec's VisualIdentity table
— doing so would create a second, driftable copy of data Phase 10
already owns ("Reuse Phase 10... Do not duplicate item mechanics",
spec, mandatory).

The ONE thing VisualIdentity legitimately holds for an item is
`signature_ornamentation` — real per-item flavor (spec's own
"restrained ornamentation... unless Canon supports it" allowance for
exceptional/named items) that has no mechanical column anywhere.
Ordinary items simply never get one set, which is the correct,
literal expression of "ordinary items should look ordinary" (spec,
mandatory) — ItemVisualSpec.signature_ornamentation is None for the
overwhelming majority of items, not a placeholder waiting to be
filled in.

No quality-to-rarity-color mapping exists anywhere in this module on
purpose: quality is craftsmanship (CRUDE..MASTERWORK), never MMO
rarity colors (spec, mandatory) — that translation, if a frontend ever
wants one, belongs in presentation code (21O), never baked into the
spec itself.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import ItemType
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.weapon import ItemWeaponProfile
from app.game.items.durability import get_item_condition
from app.game.visual.spec import get_visual_spec


class ItemVisualIdentityError(ValueError):
    pass


@dataclass(frozen=True)
class ItemVisualSpec:
    item_instance_id: str
    definition_id: str
    name: str
    item_type: str
    weapon_family: str | None
    material: str | None
    quality: str
    condition: str | None
    equipped_slot: str | None
    signature_ornamentation: str | None
    # Phase 21Q — opaque reference to a FUTURE ITEM_ILLUSTRATION asset,
    # always None until a later generation phase actually sets one via
    # app.game.visual.spec.set_visual_asset_reference. The frontend
    # must render a placeholder whenever this is None.
    asset_ref: str | None


def build_item_visual_spec(db: Session, item_instance_id: str) -> ItemVisualSpec:
    instance = db.get(ItemInstance, item_instance_id)
    if instance is None:
        raise ItemVisualIdentityError(f"Item instance {item_instance_id} does not exist.")

    definition = db.get(ItemDefinition, instance.definition_id)
    if definition is None:
        raise ItemVisualIdentityError(f"Item definition {instance.definition_id} does not exist.")

    weapon_family = None
    if definition.type == ItemType.WEAPON.value:
        weapon_profile = db.get(ItemWeaponProfile, definition.id)
        if weapon_profile is not None:
            weapon_family = weapon_profile.weapon_family

    condition = get_item_condition(instance)
    material_name = instance.material.name if instance.material is not None else None

    definition_visual = get_visual_spec(db, "item_definition", definition.id)

    return ItemVisualSpec(
        item_instance_id=instance.id,
        definition_id=definition.id,
        name=definition.name,
        item_type=definition.type,
        weapon_family=weapon_family,
        material=material_name,
        quality=instance.quality,
        condition=condition.value if condition is not None else None,
        equipped_slot=instance.equipped_slot,
        signature_ornamentation=definition_visual.stable.get("signature_ornamentation"),
        asset_ref=definition_visual.assets.get("ITEM_ILLUSTRATION"),
    )
