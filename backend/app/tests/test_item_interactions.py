import json

import pytest

from app.ai.intent_parser import Intent, _decode_response
from app.core.enums import (
    ActionIntentType,
    EquipmentSlot,
    EventType,
    ItemInstanceMode,
    ItemLocationType,
    ItemOwnerType,
    ItemQuality,
    ItemType,
    TravelPace,
)
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.db.models.location import Location
from app.game import engine
from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item
from app.game.items.containers import (
    configure_item_container_profile,
)
from app.game.items.equipment import configure_item_equipment_profile
from app.game.items.interactions import (
    ItemInteractionError,
    resolve_item_interaction,
)
from app.game.items.service import (
    create_item_definition,
    create_item_instance,
    move_item_instance,
    set_item_owner,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _world(db_session):
    campaign = create_campaign(db_session, "Interactions")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session, campaign.id, "Logan", region.id, location.id
    )
    npc = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Osgar",
    )
    db_session.add(npc)
    db_session.flush()
    return campaign, location, character, npc


def _ground_sword(db_session, location):
    definition = create_item_definition(
        db_session,
        key="interaction_sword",
        name="Espada de Ferro",
        item_type=ItemType.WEAPON,
        instance_mode=ItemInstanceMode.UNIQUE,
    )
    configure_item_equipment_profile(
        db_session, definition, allowed_slots={EquipmentSlot.MAIN_HAND}
    )
    sword = create_item_instance(db_session, definition)
    move_item_instance(
        db_session,
        sword,
        location_type=ItemLocationType.WORLD_LOCATION,
        location_ref=location.id,
    )
    return sword


def _container(db_session, character, name, capacity=20):
    definition = get_or_create_item(
        db_session, name, ItemType.CONTAINER.value, base_weight=1
    )
    configure_item_container_profile(
        db_session, definition, weight_capacity=capacity
    )
    return add_item(db_session, character.id, name)


def _interact(db_session, campaign, character, interaction, target, **kwargs):
    return resolve_item_interaction(
        db_session,
        campaign.id,
        character,
        interaction=interaction,
        target=target,
        **kwargs,
    )


def test_pick_up_drop_equip_and_unequip_are_authoritative(db_session):
    campaign, location, character, npc = _world(db_session)
    sword = _ground_sword(db_session, location)
    set_item_owner(
        db_session, sword, owner_type=ItemOwnerType.NPC, owner_ref=npc.id
    )

    _interact(
        db_session, campaign, character, ActionIntentType.PICK_UP, "Espada"
    )
    assert sword.location_type == ItemLocationType.CHARACTER.value
    assert sword.owner_ref == npc.id

    _interact(
        db_session,
        campaign,
        character,
        ActionIntentType.EQUIP,
        sword.id,
        slot="MAIN_HAND",
    )
    assert sword.equipped_slot == EquipmentSlot.MAIN_HAND.value

    with pytest.raises(ItemInteractionError, match="unequipped first"):
        _interact(
            db_session, campaign, character, ActionIntentType.DROP, sword.id
        )

    _interact(
        db_session, campaign, character, ActionIntentType.UNEQUIP, sword.id
    )
    _interact(db_session, campaign, character, ActionIntentType.DROP, sword.id)
    assert sword.location_type == ItemLocationType.WORLD_LOCATION.value
    assert sword.location_ref == location.id
    assert sword.owner_ref == npc.id


def test_store_move_between_containers_and_retrieve(db_session):
    campaign, _location, character, _npc = _world(db_session)
    backpack = _container(db_session, character, "Mochila")
    pouch = _container(db_session, character, "Bolsa")
    bread = add_item(db_session, character.id, "Pão", quantity=2)

    _interact(
        db_session,
        campaign,
        character,
        ActionIntentType.STORE,
        bread.id,
        secondary_target=backpack.id,
    )
    assert bread.location_ref == backpack.id

    _interact(
        db_session,
        campaign,
        character,
        ActionIntentType.MOVE_BETWEEN_CONTAINERS,
        bread.id,
        secondary_target=pouch.id,
    )
    assert bread.location_ref == pouch.id

    _interact(
        db_session, campaign, character, ActionIntentType.RETRIEVE, bread.id
    )
    assert bread.location_type == ItemLocationType.CHARACTER.value
    assert bread.location_ref == character.id


def test_failed_equip_does_not_retrieve_item_from_container(db_session):
    campaign, location, character, _npc = _world(db_session)
    backpack = _container(db_session, character, "Mochila")
    stored_sword = _ground_sword(db_session, location)
    _interact(
        db_session, campaign, character, ActionIntentType.PICK_UP, stored_sword.id
    )
    _interact(
        db_session,
        campaign,
        character,
        ActionIntentType.STORE,
        stored_sword.id,
        secondary_target=backpack.id,
    )
    blocker_definition = create_item_definition(
        db_session,
        key="interaction_blocker",
        name="Adaga",
        item_type=ItemType.WEAPON,
        instance_mode=ItemInstanceMode.UNIQUE,
    )
    configure_item_equipment_profile(
        db_session,
        blocker_definition,
        allowed_slots={EquipmentSlot.MAIN_HAND},
    )
    blocker = create_item_instance(db_session, blocker_definition)
    move_item_instance(
        db_session,
        blocker,
        location_type=ItemLocationType.CHARACTER,
        location_ref=character.id,
    )
    _interact(
        db_session,
        campaign,
        character,
        ActionIntentType.EQUIP,
        blocker.id,
        slot="MAIN_HAND",
    )

    with pytest.raises(ValueError, match="already occupied"):
        _interact(
            db_session,
            campaign,
            character,
            ActionIntentType.EQUIP,
            stored_sword.id,
            slot="MAIN_HAND",
        )

    db_session.refresh(stored_sword)
    assert stored_sword.location_type == ItemLocationType.CONTAINER.value
    assert stored_sword.location_ref == backpack.id


def test_give_transfers_possession_and_ownership_while_take_preserves_owner(
    db_session,
):
    campaign, _location, character, npc = _world(db_session)
    bread = add_item(db_session, character.id, "Pão")

    _interact(
        db_session,
        campaign,
        character,
        ActionIntentType.GIVE,
        bread.id,
        secondary_target=npc.id,
    )
    assert bread.location_type == ItemLocationType.NPC.value
    assert bread.location_ref == npc.id
    assert bread.owner_type == ItemOwnerType.NPC.value
    assert bread.owner_ref == npc.id

    _interact(db_session, campaign, character, ActionIntentType.TAKE, bread.id)
    assert bread.location_type == ItemLocationType.CHARACTER.value
    assert bread.location_ref == character.id
    assert bread.owner_type == ItemOwnerType.NPC.value
    assert bread.owner_ref == npc.id


def test_interaction_key_replays_without_duplicate_transfer_or_event(db_session):
    campaign, location, character, _npc = _world(db_session)
    sword = _ground_sword(db_session, location)

    first = _interact(
        db_session,
        campaign,
        character,
        ActionIntentType.PICK_UP,
        sword.id,
        interaction_key="action:pickup:1",
    )
    second = _interact(
        db_session,
        campaign,
        character,
        ActionIntentType.PICK_UP,
        sword.id,
        interaction_key="action:pickup:1",
    )

    assert not first.replayed
    assert second.replayed
    assert second.summary == first.summary
    events = db_session.query(WorldEvent).filter(
        WorldEvent.event_type == EventType.ITEM_INTERACTION_RESOLVED.value
    )
    assert events.count() == 1
    payload = json.loads(events.one().payload_json)
    assert payload["before"]["location_type"] == "WORLD_LOCATION"
    assert payload["after"]["location_type"] == "CHARACTER"


def test_reachability_and_ambiguity_are_validated(db_session):
    campaign, location, character, _npc = _world(db_session)
    sword = _ground_sword(db_session, location)
    other_location = (
        db_session.query(Location)
        .filter(Location.region_id == character.region_id, Location.id != location.id)
        .first()
    )
    move_item_instance(
        db_session,
        sword,
        location_type=ItemLocationType.WORLD_LOCATION,
        location_ref=other_location.id,
    )
    with pytest.raises(ItemInteractionError, match="not present"):
        _interact(
            db_session, campaign, character, ActionIntentType.PICK_UP, sword.id
        )

    add_item(db_session, character.id, "Pedra")
    add_item(
        db_session,
        character.id,
        "Pedra",
        quality=ItemQuality.GOOD,
    )
    with pytest.raises(ItemInteractionError, match="ambiguous"):
        _interact(
            db_session, campaign, character, ActionIntentType.DROP, "Pedra"
        )


def test_parser_extracts_item_destination_and_slot():
    decoded = _decode_response(
        '{"intent":"STORE","target":"poção","secondary_target":"mochila",'
        '"slot":null,"pace":"NORMAL"}'
    )
    equipped = _decode_response(
        '{"intent":"EQUIP","target":"espada","secondary_target":null,'
        '"slot":"MAIN_HAND","pace":"NORMAL"}'
    )

    assert decoded == (
        ActionIntentType.STORE,
        "poção",
        TravelPace.NORMAL,
        "mochila",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert equipped[0] == ActionIntentType.EQUIP
    assert equipped[4] == "MAIN_HAND"


def test_engine_applies_item_intent_before_narration(
    db_session, fake_llm, monkeypatch
):
    campaign, location, character, _npc = _world(db_session)
    sword = _ground_sword(db_session, location)
    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *_args, **_kwargs: Intent(
            type=ActionIntentType.PICK_UP,
            target=sword.id,
            raw_text="Pego a espada.",
        ),
    )
    observed = {}

    def narrate(_llm, mechanical_summary, _context, **_kwargs):
        observed["summary"] = mechanical_summary
        observed["location"] = sword.location_type
        return "Logan pega a espada do chão."

    monkeypatch.setattr(engine.narrator, "narrate", narrate)
    result = engine.resolve_action(
        db_session,
        fake_llm,
        campaign.id,
        character.id,
        "Pego a espada.",
        action_key="action:engine:pickup",
    )

    assert result.intent_type == "PICK_UP"
    assert observed["location"] == ItemLocationType.CHARACTER.value
    assert observed["summary"] == "Logan pega Espada de Ferro."
