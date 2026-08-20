import json

from app.ai.context_builder import build_context
from app.api.serializers import to_game_state_response
from app.core.enums import EquipmentSlot, ItemQuality, ItemType
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.inventory.service import add_item, get_or_create_item
from app.game.items.equipment import configure_item_equipment_profile, equip_item
from app.game.items.materials import seed_core_materials
from app.game.world.seed import create_campaign, seed_initial_region


def _inventory_world(db_session):
    campaign = create_campaign(db_session, "Item Context")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session, campaign.id, "Logan", region.id, location.id
    )
    seed_core_materials(db_session)
    sword_definition = get_or_create_item(
        db_session,
        "Espada de Ferro",
        ItemType.WEAPON.value,
        base_weight=3,
    )
    configure_item_equipment_profile(
        db_session,
        sword_definition,
        allowed_slots={EquipmentSlot.MAIN_HAND},
    )
    sword = add_item(
        db_session,
        character.id,
        "Espada de Ferro",
        quality=ItemQuality.GOOD,
        material_key="IRON",
    )
    sword.durability_current = 50
    equip_item(db_session, sword, slot=EquipmentSlot.MAIN_HAND)
    bread = add_item(db_session, character.id, "Pão", quantity=2, base_weight=0.5)
    rope = add_item(db_session, character.id, "Corda", base_weight=1)
    db_session.flush()
    return campaign, character, sword, bread, rope


def test_game_state_exposes_player_facing_inventory_without_hidden_mechanics(
    db_session,
):
    campaign, character, sword, bread, _rope = _inventory_world(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    response = to_game_state_response(db_session, state).model_dump(mode="json")
    encoded = json.dumps(response)
    by_id = {
        item["item_instance_id"]: item for item in response["inventory"]["items"]
    }

    assert by_id[sword.id] == {
        "item_instance_id": sword.id,
        "name": "Espada de Ferro",
        "type": "WEAPON",
        "quantity": 1,
        "quality": "GOOD",
        "condition": "WORN",
        "material_name": "Ferro",
        "equipped_slot": "MAIN_HAND",
        "accessibility": "IMMEDIATE",
        "contained_in_name": None,
    }
    assert by_id[bread.id]["quantity"] == 2
    assert response["inventory"]["total_weight"] == 5.0
    assert response["inventory"]["encumbrance"] == "NORMAL"
    assert "durability_current" not in encoded
    assert "durability_max" not in encoded
    assert "weight_factor" not in encoded
    assert "wear_resistance" not in encoded


def test_narrator_receives_equipment_and_only_mentioned_inventory_items(db_session):
    campaign, character, _sword, _bread, _rope = _inventory_world(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    ordinary = build_context(db_session, state, player_input="Olho ao redor.")
    bread_context = build_context(
        db_session, state, player_input="Eu examino o pão que carrego."
    )

    ordinary_items = ordinary.split("RELEVANT INVENTORY AND EQUIPMENT", 1)[1].split(
        "CURRENT WORLD", 1
    )[0]
    assert "Espada de Ferro" in ordinary_items
    assert "equipped=MAIN_HAND" in ordinary_items
    assert "Pão" not in ordinary_items
    assert "Corda" not in ordinary_items
    assert "durability=" not in ordinary_items.casefold()
    assert "durability_current" not in ordinary_items

    relevant_items = bread_context.split(
        "RELEVANT INVENTORY AND EQUIPMENT", 1
    )[1].split("CURRENT WORLD", 1)[0]
    assert "Espada de Ferro" in relevant_items
    assert "Pão: quantity=2" in relevant_items
    assert "Corda" not in relevant_items


def test_broad_inventory_request_gets_bounded_readable_summary(db_session):
    campaign, character, _sword, _bread, _rope = _inventory_world(db_session)
    for index in range(15):
        add_item(db_session, character.id, f"Objeto {index}")
    state = build_game_state(db_session, campaign.id, character.id)

    context = build_context(
        db_session,
        state,
        player_input="O que tenho no meu inventário?",
    )
    item_context = context.split("RELEVANT INVENTORY AND EQUIPMENT", 1)[1].split(
        "CURRENT WORLD", 1
    )[0]

    assert "Load state: NORMAL" in item_context
    assert "additional entries omitted from prompt" in item_context
    assert item_context.count("\n- ") <= 13
    assert "hidden item bonuses" in item_context


def test_irrelevant_unequipped_inventory_section_is_omitted(db_session):
    campaign = create_campaign(db_session, "Minimal Context")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session, campaign.id, "Logan", region.id, location.id
    )
    add_item(db_session, character.id, "Pão")
    state = build_game_state(db_session, campaign.id, character.id)

    context = build_context(db_session, state, player_input="Olho para o céu.")

    assert "RELEVANT INVENTORY AND EQUIPMENT" not in context
    assert "Pão" not in context
