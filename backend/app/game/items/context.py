from dataclasses import dataclass
import re
import unicodedata

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    EncumbranceTier,
    EquipmentSlot,
    ItemAccessibility,
    ItemCondition,
    ItemQuality,
)
from app.db.models.character import CharacterAttribute
from app.db.models.item import ItemInstance
from app.db.models.material import MaterialDefinition
from app.game.inventory.service import list_inventory
from app.game.items.durability import get_item_condition
from app.game.items.encumbrance import (
    calculate_encumbrance,
    get_carried_weight,
    get_character_encumbrance,
)
from app.game.items.equipment import resolve_item_accessibility


MAX_NARRATOR_ITEMS = 12
_BROAD_INVENTORY_CUES = (
    "inventario",
    "equipamento",
    "o que carrego",
    "o que tenho",
    "minhas coisas",
    "meus itens",
)


@dataclass(frozen=True)
class SystemInventoryItem:
    item_instance_id: str
    name: str
    type: str
    quantity: int
    quality: ItemQuality
    condition: ItemCondition | None
    material_name: str | None
    equipped_slot: EquipmentSlot | None
    accessibility: ItemAccessibility
    contained_in_name: str | None


@dataclass(frozen=True)
class SystemInventorySnapshot:
    items: tuple[SystemInventoryItem, ...]
    total_weight: float
    carrying_capacity: float
    encumbrance: EncumbranceTier


def build_system_inventory(
    db: Session,
    character_id: str,
) -> SystemInventorySnapshot:
    items = tuple(_system_item(db, entry) for entry in list_inventory(db, character_id))
    has_strength = (
        db.query(CharacterAttribute.id)
        .filter(
            CharacterAttribute.character_id == character_id,
            CharacterAttribute.key == CharacterAttributeKey.STRENGTH.value,
        )
        .first()
        is not None
    )
    if has_strength:
        load = get_character_encumbrance(db, character_id)
    else:
        # Compatibility for pre-Phase-8/fixture characters without persisted
        # attributes. New characters always own the canonical base attributes.
        load = calculate_encumbrance(get_carried_weight(db, character_id), strength=10)
    return SystemInventorySnapshot(
        items=items,
        total_weight=load.total_weight,
        carrying_capacity=load.carrying_capacity,
        encumbrance=load.tier,
    )


def build_narrator_inventory_context(
    inventory: SystemInventorySnapshot,
    player_input: str,
) -> str | None:
    normalized_input = _normalized(player_input)
    broad_request = any(
        re.search(rf"\b{re.escape(cue)}\b", normalized_input)
        for cue in _BROAD_INVENTORY_CUES
    )
    selected = []
    for item in inventory.items:
        if item.equipped_slot is not None or broad_request or _item_is_mentioned(
            item.name, normalized_input
        ):
            selected.append(item)
    selected = selected[:MAX_NARRATOR_ITEMS]
    if not selected and not broad_request:
        return None
    lines = [
        "RELEVANT INVENTORY AND EQUIPMENT",
        *([_narrator_item_line(item) for item in selected] or ["- none carried"]),
    ]
    if broad_request:
        lines.append(
            f"Load state: {inventory.encumbrance.value} "
            f"({inventory.total_weight:g}/{inventory.carrying_capacity:g} weight)"
        )
        if len(inventory.items) > len(selected):
            lines.append(
                f"- {len(inventory.items) - len(selected)} additional entries omitted from prompt"
            )
    lines.append(
        "Condition is qualitative. Do not invent durability numbers or hidden item bonuses."
    )
    return "\n".join(lines)


def _system_item(db: Session, entry: ItemInstance) -> SystemInventoryItem:
    material = (
        db.get(MaterialDefinition, entry.material_id)
        if entry.material_id is not None
        else None
    )
    parent = (
        db.get(ItemInstance, entry.location_ref)
        if entry.location_type == "CONTAINER" and entry.location_ref
        else None
    )
    return SystemInventoryItem(
        item_instance_id=entry.id,
        name=entry.definition.name,
        type=entry.definition.type,
        quantity=entry.quantity,
        quality=ItemQuality(entry.quality),
        condition=get_item_condition(entry),
        material_name=material.name if material else None,
        equipped_slot=(
            EquipmentSlot(entry.equipped_slot) if entry.equipped_slot else None
        ),
        accessibility=resolve_item_accessibility(db, entry),
        contained_in_name=(parent.definition.name if parent else None),
    )


def _narrator_item_line(item: SystemInventoryItem) -> str:
    details = [
        f"quantity={item.quantity}",
        f"quality={item.quality.value}",
        f"access={item.accessibility.value}",
    ]
    if item.condition is not None:
        details.append(f"condition={item.condition.value}")
    if item.material_name:
        details.append(f"material={item.material_name}")
    if item.equipped_slot is not None:
        details.append(f"equipped={item.equipped_slot.value}")
    if item.contained_in_name:
        details.append(f"inside={item.contained_in_name}")
    return f"- {item.name}: " + "; ".join(details)


def _item_is_mentioned(name: str, normalized_input: str) -> bool:
    words = {
        word
        for word in re.findall(r"[a-z0-9]+", _normalized(name))
        if len(word) >= 3 and word not in {"com", "das", "dos", "uma", "para"}
    }
    return any(re.search(rf"\b{re.escape(word)}\b", normalized_input) for word in words)


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
