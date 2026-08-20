import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    ItemCondition,
    ItemQuality,
    ItemType,
    ItemWearSeverity,
)
from app.db.models.item import ItemInstance, ItemWearRecord
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


DEFAULT_DURABILITY = 100.0
DURABLE_ITEM_TYPES = frozenset(
    {ItemType.WEAPON, ItemType.ARMOR, ItemType.TOOL, ItemType.CONTAINER}
)
WEAR_BY_SEVERITY = {
    ItemWearSeverity.NEGLIGIBLE: 0.0,
    ItemWearSeverity.LIGHT: 5.0,
    ItemWearSeverity.MODERATE: 15.0,
    ItemWearSeverity.SEVERE: 30.0,
    ItemWearSeverity.DEVASTATING: 100.0,
}
QUALITY_WEAR_MULTIPLIER = {
    ItemQuality.CRUDE: 1.25,
    ItemQuality.POOR: 1.10,
    ItemQuality.STANDARD: 1.0,
    ItemQuality.GOOD: 0.90,
    ItemQuality.EXCELLENT: 0.75,
    ItemQuality.MASTERWORK: 0.50,
}
_WEAR_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class ItemDurabilityError(ValueError):
    pass


@dataclass(frozen=True)
class ItemWearResult:
    record: ItemWearRecord
    replayed: bool = False


def initial_durability(item_type: ItemType) -> float | None:
    if not isinstance(item_type, ItemType):
        raise ItemDurabilityError("Invalid item type for durability.")
    return DEFAULT_DURABILITY if item_type in DURABLE_ITEM_TYPES else None


def get_item_condition(instance: ItemInstance) -> ItemCondition | None:
    current = instance.durability_current
    maximum = instance.durability_max
    if current is None and maximum is None:
        return None
    if current is None or maximum is None or maximum <= 0 or not 0 <= current <= maximum:
        raise ItemDurabilityError("Persisted item durability is invalid.")
    ratio = current / maximum
    if ratio <= 0:
        return ItemCondition.BROKEN
    if ratio < 0.20:
        return ItemCondition.CRITICAL
    if ratio < 0.40:
        return ItemCondition.DAMAGED
    if ratio < 0.70:
        return ItemCondition.WORN
    if ratio < 0.90:
        return ItemCondition.GOOD
    return ItemCondition.EXCELLENT


def is_item_broken(instance: ItemInstance) -> bool:
    return get_item_condition(instance) == ItemCondition.BROKEN


def apply_item_wear(
    db: Session,
    instance: ItemInstance,
    *,
    wear_key: str,
    severity: ItemWearSeverity,
    cause: str,
) -> ItemWearResult:
    if db.get(ItemInstance, instance.id) is None:
        raise ItemDurabilityError("Item instance does not exist.")
    normalized_key = wear_key.strip()
    normalized_cause = cause.strip()
    if not _WEAR_KEY_PATTERN.fullmatch(normalized_key):
        raise ItemDurabilityError("Invalid item wear key.")
    if not isinstance(severity, ItemWearSeverity):
        raise ItemDurabilityError("Invalid item wear severity.")
    if not normalized_cause:
        raise ItemDurabilityError("Item wear cause is required.")
    existing = (
        db.query(ItemWearRecord)
        .filter(
            ItemWearRecord.item_instance_id == instance.id,
            ItemWearRecord.wear_key == normalized_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.severity != severity.value or existing.cause != normalized_cause:
            raise ItemDurabilityError("Wear key already belongs to another event.")
        return ItemWearResult(existing, replayed=True)
    condition_before = get_item_condition(instance)
    if condition_before is None:
        raise ItemDurabilityError("Item category does not use durability.")
    if instance.campaign_id is None:
        raise ItemDurabilityError("Item must exist in a campaign before it can wear.")
    quality = ItemQuality(instance.quality)
    requested_wear = WEAR_BY_SEVERITY[severity] * QUALITY_WEAR_MULTIPLIER[quality]
    before = float(instance.durability_current)
    after = max(0.0, before - requested_wear)
    actual_wear = before - after
    instance.durability_current = after
    condition_after = get_item_condition(instance)
    record = ItemWearRecord(
        item_instance_id=instance.id,
        wear_key=normalized_key,
        severity=severity.value,
        cause=normalized_cause,
        wear_amount=actual_wear,
        durability_before=before,
        durability_after=after,
        condition_before=condition_before.value,
        condition_after=condition_after.value,
        created_world_minute=get_world_time(db, instance.campaign_id).total_minutes(),
    )
    db.add(record)
    db.flush()
    payload = {
        "item_instance_id": instance.id,
        "definition_id": instance.definition_id,
        "wear_key": normalized_key,
        "severity": severity.value,
        "cause": normalized_cause,
        "quality": quality.value,
        "wear_amount": actual_wear,
        "condition_before": condition_before.value,
        "condition_after": condition_after.value,
    }
    log_event(
        db,
        instance.campaign_id,
        EventType.ITEM_WEAR_APPLIED,
        actor_type="item_instance",
        actor_id=instance.id,
        payload=payload,
    )
    if condition_before != ItemCondition.BROKEN and condition_after == ItemCondition.BROKEN:
        log_event(
            db,
            instance.campaign_id,
            EventType.ITEM_BROKEN,
            actor_type="item_instance",
            actor_id=instance.id,
            payload=payload,
        )
    db.flush()
    return ItemWearResult(record)
