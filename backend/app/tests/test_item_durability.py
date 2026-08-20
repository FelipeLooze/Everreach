import json

import pytest

from app.core.enums import (
    EventType,
    ItemCondition,
    ItemQuality,
    ItemType,
    ItemWearSeverity,
)
from app.db.models.event import WorldEvent
from app.db.models.item import ItemInstance
from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item
from app.game.items.durability import (
    ItemDurabilityError,
    apply_item_wear,
    get_item_condition,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session):
    campaign = create_campaign(db_session, "Durability")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session, campaign.id, "Hero", region.id, location.id
    )
    return campaign, character


@pytest.mark.parametrize(
    ("durability", "condition"),
    [
        (100, ItemCondition.EXCELLENT),
        (89, ItemCondition.GOOD),
        (69, ItemCondition.WORN),
        (39, ItemCondition.DAMAGED),
        (19, ItemCondition.CRITICAL),
        (0, ItemCondition.BROKEN),
    ],
)
def test_condition_is_a_stable_player_facing_durability_band(durability, condition):
    instance = ItemInstance(
        definition_id="item_test",
        durability_current=durability,
        durability_max=100,
    )
    assert get_item_condition(instance) == condition


def test_wear_is_event_driven_idempotent_and_quality_affects_only_wear(db_session):
    campaign, character = _character(db_session)
    get_or_create_item(db_session, "Martelo Padrão", ItemType.TOOL.value)
    get_or_create_item(db_session, "Martelo Excelente", ItemType.TOOL.value)
    standard = add_item(db_session, character.id, "Martelo Padrão")
    excellent = add_item(
        db_session,
        character.id,
        "Martelo Excelente",
        quality=ItemQuality.EXCELLENT,
    )

    standard_result = apply_item_wear(
        db_session,
        standard,
        wear_key="impact:stone:1",
        severity=ItemWearSeverity.MODERATE,
        cause="struck stone",
    )
    excellent_result = apply_item_wear(
        db_session,
        excellent,
        wear_key="impact:stone:1",
        severity=ItemWearSeverity.MODERATE,
        cause="struck stone",
    )
    replay = apply_item_wear(
        db_session,
        standard,
        wear_key="impact:stone:1",
        severity=ItemWearSeverity.MODERATE,
        cause="struck stone",
    )

    assert standard_result.record.wear_amount == 15
    assert excellent_result.record.wear_amount == 11.25
    assert standard.durability_current == 85
    assert excellent.durability_current == 88.75
    assert get_item_condition(standard) == ItemCondition.GOOD
    assert replay.replayed is True
    assert standard.durability_current == 85
    events = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.ITEM_WEAR_APPLIED.value)
        .all()
    )
    assert len(events) == 2
    assert json.loads(events[0].payload_json)["condition_after"] == "GOOD"
    assert all(event.campaign_id == campaign.id for event in events)


def test_negligible_use_does_not_create_arbitrary_wear_and_breakage_is_authoritative(
    db_session,
):
    _campaign, character = _character(db_session)
    get_or_create_item(db_session, "Picareta", ItemType.TOOL.value)
    item = add_item(db_session, character.id, "Picareta")
    negligible = apply_item_wear(
        db_session,
        item,
        wear_key="normal-use:1",
        severity=ItemWearSeverity.NEGLIGIBLE,
        cause="normal use",
    )
    broken = apply_item_wear(
        db_session,
        item,
        wear_key="collapse:1",
        severity=ItemWearSeverity.DEVASTATING,
        cause="buried by a rock collapse",
    )

    assert negligible.record.wear_amount == 0
    assert item.durability_current == 0
    assert broken.record.condition_after == ItemCondition.BROKEN.value
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.ITEM_BROKEN.value)
        .count()
        == 1
    )


def test_non_durable_item_rejects_wear(db_session):
    _campaign, character = _character(db_session)
    bread = add_item(db_session, character.id, "Pão")
    assert get_item_condition(bread) is None
    with pytest.raises(ItemDurabilityError, match="does not use durability"):
        apply_item_wear(
            db_session,
            bread,
            wear_key="use:1",
            severity=ItemWearSeverity.LIGHT,
            cause="ordinary handling",
        )
