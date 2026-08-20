import json

import pytest

from app.core.enums import (
    EquipmentSlot,
    EventType,
    ItemAccessibility,
    ItemLocationType,
)
from app.db.models.event import WorldEvent
from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item
from app.game.items.equipment import (
    EquipmentError,
    configure_item_equipment_profile,
    equip_item,
    get_allowed_equipment_slots,
    item_accessibility,
    unequip_item,
)
from app.game.items.service import ItemFoundationError, move_item_instance
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session):
    campaign = create_campaign(db_session, "Equipment")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    return campaign, character


def _equippable(db_session, character_id, name, item_type, slots):
    definition = get_or_create_item(db_session, name, item_type)
    profile = configure_item_equipment_profile(
        db_session,
        definition,
        allowed_slots=set(slots),
    )
    instance = add_item(db_session, character_id, name)
    return definition, profile, instance


def test_equipment_profile_is_canonical_and_obeys_item_category_rules(db_session):
    _campaign, character = _character(db_session)
    _sword, profile, _instance = _equippable(
        db_session,
        character.id,
        "Espada Longa",
        "weapon",
        {EquipmentSlot.MAIN_HAND, EquipmentSlot.WAIST},
    )

    assert get_allowed_equipment_slots(profile) == {
        EquipmentSlot.MAIN_HAND,
        EquipmentSlot.WAIST,
    }
    with pytest.raises(EquipmentError, match="different canonical"):
        configure_item_equipment_profile(
            db_session,
            profile.item,
            allowed_slots={EquipmentSlot.BACK},
        )

    backpack = get_or_create_item(db_session, "Mochila", "container")
    with pytest.raises(EquipmentError, match="cannot use slots"):
        configure_item_equipment_profile(
            db_session,
            backpack,
            allowed_slots={EquipmentSlot.MAIN_HAND},
        )


def test_equipping_changes_physical_slot_accessibility_and_emits_events(db_session):
    _campaign, character = _character(db_session)
    _definition, _profile, sword = _equippable(
        db_session,
        character.id,
        "Espada Longa",
        "weapon",
        {EquipmentSlot.MAIN_HAND, EquipmentSlot.WAIST},
    )

    equip_item(db_session, sword, slot=EquipmentSlot.WAIST)
    assert sword.location_type == ItemLocationType.CHARACTER_EQUIPPED.value
    assert sword.equipped_slot == EquipmentSlot.WAIST.value
    assert item_accessibility(sword) == ItemAccessibility.QUICK

    equip_item(db_session, sword, slot=EquipmentSlot.MAIN_HAND)
    equip_item(db_session, sword, slot=EquipmentSlot.MAIN_HAND)
    assert sword.equipped_slot == EquipmentSlot.MAIN_HAND.value
    assert item_accessibility(sword) == ItemAccessibility.IMMEDIATE

    equipped_events = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.ITEM_EQUIPPED.value)
        .order_by(WorldEvent.created_at)
        .all()
    )
    assert len(equipped_events) == 2
    assert json.loads(equipped_events[-1].payload_json)["previous_slot"] == "WAIST"

    unequip_item(db_session, sword)
    assert sword.location_type == ItemLocationType.CHARACTER.value
    assert sword.equipped_slot is None
    assert item_accessibility(sword) == ItemAccessibility.STOWED
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.ITEM_UNEQUIPPED.value)
        .count()
        == 1
    )


def test_two_handed_position_reserves_both_hands(db_session):
    _campaign, character = _character(db_session)
    _great, _profile, greatsword = _equippable(
        db_session,
        character.id,
        "Montante",
        "weapon",
        {EquipmentSlot.BOTH_HANDS, EquipmentSlot.BACK},
    )
    _shield, _profile, shield = _equippable(
        db_session,
        character.id,
        "Escudo",
        "armor",
        {EquipmentSlot.OFF_HAND, EquipmentSlot.BACK},
    )
    _sword, _profile, sword = _equippable(
        db_session,
        character.id,
        "Espada Curta",
        "weapon",
        {EquipmentSlot.MAIN_HAND, EquipmentSlot.WAIST},
    )

    equip_item(db_session, shield, slot=EquipmentSlot.OFF_HAND)
    with pytest.raises(EquipmentError, match="already occupied"):
        equip_item(db_session, greatsword, slot=EquipmentSlot.BOTH_HANDS)
    unequip_item(db_session, shield)
    equip_item(db_session, greatsword, slot=EquipmentSlot.BOTH_HANDS)
    with pytest.raises(EquipmentError, match="already occupied"):
        equip_item(db_session, sword, slot=EquipmentSlot.MAIN_HAND)

    assert greatsword.equipped_slot == EquipmentSlot.BOTH_HANDS.value
    assert shield.equipped_slot is None


def test_equipment_service_cannot_be_bypassed_by_generic_item_movement(db_session):
    _campaign, character = _character(db_session)
    _definition, _profile, sword = _equippable(
        db_session,
        character.id,
        "Espada",
        "weapon",
        {EquipmentSlot.MAIN_HAND},
    )

    with pytest.raises(ItemFoundationError, match="equipment service"):
        move_item_instance(
            db_session,
            sword,
            location_type=ItemLocationType.CHARACTER_EQUIPPED,
            location_ref=character.id,
        )
    equip_item(db_session, sword, slot=EquipmentSlot.MAIN_HAND)
    with pytest.raises(ItemFoundationError, match="unequipped"):
        move_item_instance(
            db_session,
            sword,
            location_type=ItemLocationType.CHARACTER,
            location_ref=character.id,
        )


def test_inventory_api_exposes_instance_slot_and_accessibility(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Equipment API"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters",
        json={"name": "Hero"},
    ).json()
    _definition, _profile, sword = _equippable(
        db_session,
        character["id"],
        "Espada de Teste",
        "weapon",
        {EquipmentSlot.MAIN_HAND, EquipmentSlot.WAIST},
    )
    equip_item(db_session, sword, slot=EquipmentSlot.MAIN_HAND)

    response = client.get(
        f"/api/campaigns/{campaign['id']}/inventory",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["item_instance_id"] == sword.id
    assert item["equipped"] is True
    assert item["equipped_slot"] == "MAIN_HAND"
    assert item["accessibility"] == "IMMEDIATE"
    assert item["allowed_slots"] == ["MAIN_HAND", "WAIST"]
