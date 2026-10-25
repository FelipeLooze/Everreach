"""Playable A2b flow: harvest a real carcass, then sell authoritative loot."""

import random

import pytest

from app.core.enums import (
    CombatActorType,
    ItemLocationType,
    ItemOwnerType,
    NPCActivity,
)
from app.db.models.character import Character
from app.db.models.item import ItemDefinition
from app.db.models.loot import CreatureHarvestResolution
from app.db.models.npc import NPC
from app.db.models.shop import Shop
from app.game import engine
from app.game.creatures import population
from app.game.creatures.loot_catalog import (
    FOOD_AND_HIDE,
    HARD_MATERIAL,
    all_bestiary_items,
    ensure_bestiary_item_definitions,
)
from app.game.creatures.species import all_species
from app.game.economy.shops import ShopError, quote_shop_purchase, sell_to_shop
from app.game.items.service import (
    create_item_instance,
    move_item_instance,
    set_item_owner,
)
from app.game.time import clock


def _world(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Coleta A2b"}).json()
    data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(
        f"/api/campaigns/{campaign['id']}/start",
        params={"character_id": data["id"]},
    )
    return campaign["id"], db_session.get(Character, data["id"])


def _dead_rat(db_session, campaign_id, character):
    species = next(
        entry for entry in all_species().values()
        if entry.singular == "Rato de Celeiro"
    )
    from app.db.models.location import Location

    place = db_session.get(Location, character.location_id)
    creature = population._spawn(
        db_session,
        campaign_id,
        place,
        species,
        "proxima",
        random.Random(3),
        12,
    )
    creature.alive = False
    creature.hp_current = 0
    creature.activity = NPCActivity.AVAILABLE.value
    creature.died_world_minute = clock.get_world_time(
        db_session, campaign_id
    ).total_minutes()
    db_session.flush()
    return creature


def _give(db_session, character, definition, quantity=1):
    item = create_item_instance(db_session, definition, quantity=quantity)
    move_item_instance(
        db_session,
        item,
        location_type=ItemLocationType.CHARACTER,
        location_ref=character.id,
    )
    set_item_owner(
        db_session,
        item,
        owner_type=ItemOwnerType.CHARACTER,
        owner_ref=character.id,
    )
    return item


def test_bestiary_materializes_all_unique_loot_items(db_session):
    catalog = all_bestiary_items()
    definitions = ensure_bestiary_item_definitions(db_session)

    assert len(catalog) == 713
    assert len(definitions) == 713
    assert all(isinstance(value, ItemDefinition) for value in definitions.values())
    assert all(
        definition.base_value_bronze
        == catalog[key].effective_price_bronze
        for key, definition in definitions.items()
    )


def test_natural_language_harvest_requires_a_cutting_tool_and_is_per_method(
    client, db_session, fake_llm, monkeypatch
):
    campaign_id, character = _world(client, db_session)
    rat = _dead_rat(db_session, campaign_id, character)
    monkeypatch.setattr(
        "app.game.items.loot.effective_drop_chance", lambda _chance, _luck: 1.0
    )

    refused = engine.resolve_action(
        db_session,
        fake_llm,
        campaign_id,
        character.id,
        "Esfolo o rato de celeiro.",
        intent_llm_service=fake_llm,
    )
    assert "ferramenta de corte" in refused.mechanical_summary
    assert db_session.query(CreatureHarvestResolution).count() == 0

    knife = db_session.query(ItemDefinition).filter(
        ItemDefinition.key == "economy_iron_knife"
    ).one()
    _give(db_session, character, knife)
    harvested = engine.resolve_action(
        db_session,
        fake_llm,
        campaign_id,
        character.id,
        "Esfolo o rato de celeiro.",
        intent_llm_service=fake_llm,
    )
    assert harvested.intent_type == "LOOT"
    assert "obtém:" in harvested.mechanical_summary
    assert db_session.query(CreatureHarvestResolution).filter(
        CreatureHarvestResolution.source_npc_id == rat.id,
        CreatureHarvestResolution.harvest_method == "esfolar",
    ).count() == 1

    repeated = engine.resolve_action(
        db_session,
        fake_llm,
        campaign_id,
        character.id,
        "Esfolo o rato novamente.",
        intent_llm_service=fake_llm,
    )
    assert "já foi usado" in repeated.mechanical_summary

    second_method = engine.resolve_action(
        db_session,
        fake_llm,
        campaign_id,
        character.id,
        "Recolho a cauda do rato.",
        intent_llm_service=fake_llm,
    )
    assert "obtém:" in second_method.mechanical_summary
    assert db_session.query(CreatureHarvestResolution).filter(
        CreatureHarvestResolution.source_npc_id == rat.id
    ).count() == 2


def test_specialists_and_merchants_offer_dataset_prices_with_finite_cash(
    client, db_session
):
    campaign_id, character = _world(client, db_session)
    catalog = all_bestiary_items()
    definitions = ensure_bestiary_item_definitions(db_session)
    hide = next(
        item for item in catalog.values()
        if FOOD_AND_HIDE in item.purchase_categories and item.effective_price_bronze > 1
    )
    hard = next(
        item for item in catalog.values()
        if HARD_MATERIAL in item.purchase_categories and item.effective_price_bronze > 1
    )
    unsellable = next(item for item in catalog.values() if not item.sellable)

    general = db_session.query(Shop).filter(Shop.name.like("Loja Geral de %")).one()
    smith = db_session.query(Shop).filter(Shop.name.like("Ferraria de %")).one()
    guild = db_session.query(Shop).filter(
        Shop.name == "Entreposto da Guilda de Comerciantes"
    ).one()

    hide_item = _give(db_session, character, definitions[hide.key])
    assert quote_shop_purchase(db_session, general, hide_item) == hide.effective_price_bronze
    assert quote_shop_purchase(db_session, smith, hide_item) is None
    guild_price = quote_shop_purchase(db_session, guild, hide_item)
    assert 0 < guild_price < hide.effective_price_bronze

    hard_item = _give(db_session, character, definitions[hard.key])
    assert quote_shop_purchase(db_session, smith, hard_item) == hard.effective_price_bronze
    no_value = _give(db_session, character, definitions[unsellable.key])
    assert quote_shop_purchase(db_session, guild, no_value) is None

    general.till_bronze = hide.effective_price_bronze - 1
    with pytest.raises(ShopError, match="fundos suficientes"):
        sell_to_shop(
            db_session,
            general,
            hide_item,
            seller_type=CombatActorType.CHARACTER,
            seller_id=character.id,
        )
    general.till_bronze = hide.effective_price_bronze
    paid = sell_to_shop(
        db_session,
        general,
        hide_item,
        seller_type=CombatActorType.CHARACTER,
        seller_id=character.id,
    )
    assert paid == hide.effective_price_bronze
    assert general.till_bronze == 0


def test_player_can_sell_a_hide_by_describing_the_person_at_the_counter(
    client, db_session, fake_llm
):
    from app.game.economy.wallet import total_carried_by_owner

    campaign_id, character = _world(client, db_session)
    catalog = all_bestiary_items()
    definitions = ensure_bestiary_item_definitions(db_session)
    hide = next(
        item for item in catalog.values()
        if FOOD_AND_HIDE in item.purchase_categories
        and "pele" in item.name.casefold()
        and item.effective_price_bronze > 0
    )
    carried = _give(db_session, character, definitions[hide.key])
    general = db_session.query(Shop).filter(Shop.name.like("Loja Geral de %")).one()
    operator = db_session.get(NPC, general.operator_id)
    character.location_id = general.location_id
    operator.activity = NPCActivity.WORKING.value
    operator.visiting_location_id = None
    till_before = general.till_bronze
    db_session.flush()

    result = engine.resolve_action(
        db_session,
        fake_llm,
        campaign_id,
        character.id,
        "Vendo a pele para a mulher atrás do balcão.",
        intent_llm_service=fake_llm,
    )

    assert result.intent_type == "SELL"
    assert "vende 1×" in result.mechanical_summary
    assert total_carried_by_owner(
        db_session, CombatActorType.CHARACTER, character.id
    ) == hide.effective_price_bronze
    assert general.till_bronze == till_before - hide.effective_price_bronze
    assert carried.owner_ref == general.operator_id


def test_creature_carcass_expires_after_two_world_days(client, db_session):
    campaign_id, character = _world(client, db_session)
    rat = _dead_rat(db_session, campaign_id, character)

    clock.advance_world_time(
        db_session, campaign_id, population.CORPSE_LIFETIME_MINUTES - 1
    )
    assert population.cleanup_expired_corpses(db_session, campaign_id) == 0
    clock.advance_world_time(db_session, campaign_id, 1)
    assert population.cleanup_expired_corpses(db_session, campaign_id) == 1
    assert db_session.get(NPC, rat.id) is None
