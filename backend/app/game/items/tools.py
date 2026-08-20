import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    ItemAccessibility,
    ItemCondition,
    ItemQuality,
    ItemType,
    ToolCapability,
)
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.material import MaterialDefinition
from app.db.models.tool import ItemToolProfile
from app.game.items.durability import get_item_condition, is_item_broken
from app.game.items.containers import is_item_possessed_by_character
from app.game.items.equipment import resolve_item_accessibility


class ToolError(ValueError):
    pass


@dataclass(frozen=True)
class ToolUseContext:
    instance_id: str
    capability: ToolCapability
    accessibility: ItemAccessibility
    quality: ItemQuality
    condition: ItemCondition | None
    material_key: str | None


def configure_item_tool_profile(
    db: Session,
    item: ItemDefinition,
    *,
    capabilities: set[ToolCapability],
) -> ItemToolProfile:
    if db.get(ItemDefinition, item.id) is None:
        raise ToolError("Tool item must be persisted before configuration.")
    if item.type != ItemType.TOOL.value:
        raise ToolError("Only TOOL item definitions can have a tool profile.")
    if not capabilities or any(
        not isinstance(capability, ToolCapability) for capability in capabilities
    ):
        raise ToolError("At least one valid tool capability is required.")
    encoded = _encode_capabilities(capabilities)
    existing = db.get(ItemToolProfile, item.id)
    if existing is not None:
        if existing.capabilities_json != encoded:
            raise ToolError("Item already has different canonical tool mechanics.")
        return existing
    profile = ItemToolProfile(item_id=item.id, capabilities_json=encoded)
    db.add(profile)
    db.flush()
    return profile


def get_tool_capabilities(profile: ItemToolProfile) -> frozenset[ToolCapability]:
    try:
        raw = json.loads(profile.capabilities_json)
        if not isinstance(raw, list) or not raw:
            raise ValueError
        capabilities = frozenset(ToolCapability(value) for value in raw)
        if len(capabilities) != len(raw):
            raise ValueError
        return capabilities
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ToolError("Persisted tool capabilities are invalid.") from exc


def validate_character_tool_use(
    db: Session,
    character_id: str,
    tool_instance_id: str,
    *,
    required_capability: ToolCapability,
) -> ToolUseContext:
    if not isinstance(required_capability, ToolCapability):
        raise ToolError("Invalid required tool capability.")
    instance = db.get(ItemInstance, tool_instance_id)
    if instance is None:
        raise ToolError("Tool instance does not exist.")
    if not is_item_possessed_by_character(db, instance, character_id):
        raise ToolError("Tool must be physically carried by the acting character.")
    profile = db.get(ItemToolProfile, instance.definition_id)
    if profile is None:
        raise ToolError("Item has no authoritative tool profile.")
    if is_item_broken(instance):
        raise ToolError("Broken tool cannot provide a practical capability.")
    if required_capability not in get_tool_capabilities(profile):
        raise ToolError("Tool does not provide the required capability.")
    return ToolUseContext(
        instance_id=instance.id,
        capability=required_capability,
        accessibility=resolve_item_accessibility(db, instance),
        quality=ItemQuality(instance.quality),
        condition=get_item_condition(instance),
        material_key=(
            db.get(MaterialDefinition, instance.material_id).key
            if instance.material_id is not None
            else None
        ),
    )


def _encode_capabilities(capabilities: set[ToolCapability]) -> str:
    return json.dumps(
        sorted(capability.value for capability in capabilities),
        separators=(",", ":"),
    )
