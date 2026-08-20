import json

import pytest

from app.core.enums import (
    CharacterStatus,
    EventType,
    ItemInstanceMode,
    ItemLocationType,
    ItemOwnerType,
    ItemQuality,
    ItemType,
)
from app.db.models.event import WorldEvent
from app.db.models.item import ItemInstance
from app.db.models.npc import NPC
from app.game.character.service import create_character, kill_character
from app.game.inventory.service import add_item, list_inventory
from app.game.items.service import (
    ItemFoundationError,
    create_item_definition,
    create_item_instance,
    move_item_instance,
    set_item_owner,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _world(db_session, name="Items"):
    campaign = create_campaign(db_session, name)
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session, campaign.id, "Hero", region.id, location.id
    )
    npc = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Ferreiro",
    )
    db_session.add(npc)
    db_session.flush()
    return campaign, region, location, character, npc


def _sword(db_session):
    definition = create_item_definition(
        db_session,
        key="espada_de_ferro",
        name="Espada de Ferro",
        item_type=ItemType.WEAPON,
        instance_mode=ItemInstanceMode.UNIQUE,
    )
    return create_item_instance(db_session, definition)


def test_physical_location_and_social_ownership_are_independent(db_session):
    campaign, _region, location, character, npc = _world(db_session)
    sword = _sword(db_session)
    move_item_instance(
        db_session,
        sword,
        location_type=ItemLocationType.WORLD_LOCATION,
        location_ref=location.id,
    )
    set_item_owner(
        db_session,
        sword,
        owner_type=ItemOwnerType.NPC,
        owner_ref=npc.id,
    )
    move_item_instance(
        db_session,
        sword,
        location_type=ItemLocationType.CHARACTER,
        location_ref=character.id,
    )

    assert sword.campaign_id == campaign.id
    assert sword.location_type == ItemLocationType.CHARACTER.value
    assert sword.location_ref == character.id
    assert sword.owner_type == ItemOwnerType.NPC.value
    assert sword.owner_ref == npc.id
    assert list_inventory(db_session, character.id) == [sword]

    location_events = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.ITEM_LOCATION_CHANGED.value)
        .order_by(WorldEvent.created_at)
        .all()
    )
    ownership_event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.ITEM_OWNERSHIP_CHANGED.value)
        .one()
    )
    assert len(location_events) == 2
    assert json.loads(location_events[-1].payload_json)["after"] == {
        "type": "CHARACTER",
        "ref": character.id,
        "slot": None,
    }
    assert json.loads(ownership_event.payload_json)["after"]["ref"] == npc.id


def test_item_cannot_move_to_an_entity_in_another_campaign(db_session):
    _campaign, _region, location, _character, _npc = _world(db_session, "First")
    _other_campaign, _other_region, _other_location, other_character, _other_npc = (
        _world(db_session, "Second")
    )
    sword = _sword(db_session)
    move_item_instance(
        db_session,
        sword,
        location_type=ItemLocationType.WORLD_LOCATION,
        location_ref=location.id,
    )

    with pytest.raises(ItemFoundationError, match="between campaigns"):
        move_item_instance(
            db_session,
            sword,
            location_type=ItemLocationType.CHARACTER,
            location_ref=other_character.id,
        )
    assert sword.location_type == ItemLocationType.WORLD_LOCATION.value
    assert sword.location_ref == location.id


def test_repeating_the_same_location_does_not_duplicate_events(db_session):
    _campaign, _region, location, _character, _npc = _world(db_session)
    sword = _sword(db_session)
    for _ in range(2):
        move_item_instance(
            db_session,
            sword,
            location_type=ItemLocationType.WORLD_LOCATION,
            location_ref=location.id,
        )

    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.ITEM_LOCATION_CHANGED.value)
        .count()
        == 1
    )


def test_character_death_does_not_delete_or_unplace_carried_items(db_session):
    campaign, _region, _location, character, _npc = _world(db_session)
    carried = add_item(db_session, character.id, "Pão", quantity=2)

    kill_character(db_session, campaign.id, character, cause="teste")
    db_session.flush()

    persisted = db_session.get(ItemInstance, carried.id)
    assert character.status == CharacterStatus.DEAD.value
    assert persisted is not None
    assert persisted.quantity == 2
    assert persisted.location_type == ItemLocationType.CHARACTER.value
    assert persisted.location_ref == character.id
    assert persisted.owner_type == ItemOwnerType.CHARACTER.value


def test_stackable_items_only_merge_when_quality_matches(db_session):
    _campaign, _region, _location, character, _npc = _world(db_session)
    standard = add_item(
        db_session, character.id, "Pão", quantity=2, quality=ItemQuality.STANDARD
    )
    same = add_item(
        db_session, character.id, "Pão", quantity=1, quality=ItemQuality.STANDARD
    )
    good = add_item(
        db_session, character.id, "Pão", quantity=1, quality=ItemQuality.GOOD
    )

    assert same.id == standard.id
    assert standard.quantity == 3
    assert good.id != standard.id
    assert good.quality == ItemQuality.GOOD.value
    assert len(list_inventory(db_session, character.id)) == 2


def test_inventory_api_reads_item_instances_as_the_authoritative_source(
    client, db_session
):
    campaign = client.post("/api/campaigns", json={"name": "Inventory API"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Hero"}
    ).json()
    instance = add_item(db_session, character["id"], "Pão", quantity=3)

    response = client.get(
        f"/api/campaigns/{campaign['id']}/inventory",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "item_instance_id": instance.id,
            "item_id": instance.definition_id,
            "name": "Pão",
            "type": "MISC",
            "quantity": 3,
            "quality": "STANDARD",
            "condition": None,
            "material": None,
            "equipped": False,
            "unit_weight": 0.0,
            "total_weight": 0.0,
            "equipped_slot": None,
            "accessibility": "STOWED",
            "allowed_slots": [],
            "weapon": None,
            "armor": None,
            "tool": None,
        }
    ]
    assert response.json()["total_weight"] == 0.0
    assert response.json()["carrying_capacity"] == 25.0
    assert response.json()["load_ratio"] == 0.0
    assert response.json()["encumbrance"] == "NORMAL"
