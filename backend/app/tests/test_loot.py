import pytest

from app.core.enums import CharacterAttributeKey, ItemInstanceMode, ItemLocationType, ItemOwnerType, ItemType
from app.db.models.item import ItemInstance
from app.db.models.loot import LootResolution
from app.db.models.npc import NPC
from app.game.attributes.service import get_character_attribute
from app.game.character.service import create_character
from app.game.items.loot import (
    LootError, add_loot_entry, assign_npc_loot_table, create_loot_table,
    effective_drop_chance, resolve_npc_loot,
)
from app.game.items.service import create_item_definition, create_item_instance, move_item_instance, set_item_owner
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db):
    campaign = create_campaign(db, "Loot")
    region, location = seed_initial_region(db, campaign.id)
    character = create_character(db, campaign.id, "Lia", region.id, location.id)
    corpse = NPC(campaign_id=campaign.id, region_id=region.id, location_id=location.id, name="Saqueador", alive=False)
    db.add(corpse); db.flush()
    return campaign, character, corpse


def test_luck_modifies_only_loot_probability_with_a_bounded_bonus():
    assert effective_drop_chance(0.40, 10) == pytest.approx(0.40)
    assert effective_drop_chance(0.40, 15) == pytest.approx(0.45)
    assert effective_drop_chance(0.90, 99) == 1.0


def test_loot_collects_real_possessions_and_generated_table_entries_once(db_session):
    campaign, character, corpse = _setup(db_session)
    coin = create_item_definition(db_session, key="moeda_loot", name="Moeda Antiga", item_type=ItemType.MISC, instance_mode=ItemInstanceMode.STACKABLE)
    carried = create_item_instance(db_session, coin, quantity=3)
    move_item_instance(db_session, carried, location_type=ItemLocationType.NPC, location_ref=corpse.id)
    set_item_owner(db_session, carried, owner_type=ItemOwnerType.NPC, owner_ref=corpse.id)
    herb = create_item_definition(db_session, key="erva_loot", name="Erva Rubra", item_type=ItemType.MATERIAL, instance_mode=ItemInstanceMode.STACKABLE)
    table = create_loot_table(db_session, "saqueador_teste", "Saqueador de teste")
    add_loot_entry(db_session, table, herb, drop_chance=1, min_quantity=2, max_quantity=2)
    assign_npc_loot_table(db_session, corpse, table)
    get_character_attribute(db_session, character.id, CharacterAttributeKey.LUCK).value = 18

    result = resolve_npc_loot(db_session, campaign.id, character, corpse.name, action_key="loot-1")
    replay = resolve_npc_loot(db_session, campaign.id, character, corpse.name, action_key="loot-1")

    assert ("Moeda Antiga", 3) in result.items
    assert ("Erva Rubra", 2) in result.items
    assert result.luck_value == 18
    assert replay.replayed is True
    assert db_session.query(LootResolution).count() == 1
    held = db_session.query(ItemInstance).filter(ItemInstance.location_type == ItemLocationType.CHARACTER.value, ItemInstance.location_ref == character.id).all()
    assert len(held) == 2


def test_living_npc_cannot_be_looted(db_session):
    campaign, character, corpse = _setup(db_session)
    corpse.alive = True
    with pytest.raises(LootError):
        resolve_npc_loot(db_session, campaign.id, character, corpse.name, action_key="loot-living")
