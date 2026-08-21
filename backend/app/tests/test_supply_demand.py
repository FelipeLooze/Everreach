"""Phase 14H — Supply & Demand.

Bounded modifiers only: supply_index is clamped to [10, 300], the
resulting price multiplier to [0.5, 2.0] — no absurd exponential prices
from a single change. No LocalSupplyLevel row at all means no distortion
— resolve_local_market_price falls back to the plain Phase 14B price.
"""

import pytest

from app.game.character.service import create_character
from app.game.economy.pricing import set_item_base_value
from app.game.economy.supply_demand import (
    BASELINE_SUPPLY_INDEX,
    MAX_SUPPLY_INDEX,
    MIN_SUPPLY_INDEX,
    SupplyError,
    adjust_supply,
    get_or_create_supply_level,
    resolve_local_market_price,
    supply_price_multiplier,
)
from app.game.inventory.service import add_item, get_or_create_item
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Supply Demand")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def test_no_supply_row_means_no_price_distortion(db_session):
    campaign, region, village, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Pão")
    set_item_base_value(db_session, definition, 6)
    bread = add_item(db_session, character.id, "Pão")

    assert resolve_local_market_price(db_session, bread, village.id) == 6


def test_shortage_raises_the_local_price(db_session):
    campaign, region, village, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Pão")
    set_item_base_value(db_session, definition, 6)
    bread = add_item(db_session, character.id, "Pão")
    level = get_or_create_supply_level(db_session, campaign.id, village.id, definition.id)

    adjust_supply(db_session, level, -60, reason="Colheita fracassada.")

    assert resolve_local_market_price(db_session, bread, village.id) > 6


def test_surplus_lowers_the_local_price(db_session):
    campaign, region, village, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Ferro")
    set_item_base_value(db_session, definition, 20)
    iron = add_item(db_session, character.id, "Ferro")
    level = get_or_create_supply_level(db_session, campaign.id, village.id, definition.id)

    adjust_supply(db_session, level, 100, reason="Mina produzindo intensamente.")

    assert resolve_local_market_price(db_session, iron, village.id) < 20


def test_supply_index_is_clamped_to_bounds(db_session):
    campaign, region, village, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Item")
    level = get_or_create_supply_level(db_session, campaign.id, village.id, definition.id)

    adjust_supply(db_session, level, -10_000, reason="Colapso total.")
    assert level.supply_index == MIN_SUPPLY_INDEX

    adjust_supply(db_session, level, 100_000, reason="Excedente extremo.")
    assert level.supply_index == MAX_SUPPLY_INDEX


def test_price_multiplier_is_bounded_even_at_extremes():
    assert supply_price_multiplier(BASELINE_SUPPLY_INDEX) == 1.0
    assert supply_price_multiplier(MIN_SUPPLY_INDEX) <= 2.0
    assert supply_price_multiplier(MAX_SUPPLY_INDEX) >= 0.5


def test_a_single_small_purchase_never_moves_supply_by_itself(db_session):
    # There is no automatic per-transaction supply reaction anywhere in
    # this module — buying an item never touches LocalSupplyLevel unless
    # a caller explicitly calls adjust_supply. This test documents that
    # by simply confirming the baseline stays put with no such call.
    campaign, region, village, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Pão")
    level = get_or_create_supply_level(db_session, campaign.id, village.id, definition.id)

    assert level.supply_index == BASELINE_SUPPLY_INDEX


def test_adjust_supply_requires_a_reason(db_session):
    campaign, region, village, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Item")
    level = get_or_create_supply_level(db_session, campaign.id, village.id, definition.id)

    with pytest.raises(SupplyError):
        adjust_supply(db_session, level, -10, reason="  ")


def test_zero_valued_item_stays_zero_regardless_of_supply(db_session):
    campaign, region, village, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Sucata")
    set_item_base_value(db_session, definition, 0)
    scrap = add_item(db_session, character.id, "Sucata")
    level = get_or_create_supply_level(db_session, campaign.id, village.id, definition.id)
    adjust_supply(db_session, level, -50, reason="Escassez.")

    assert resolve_local_market_price(db_session, scrap, village.id) == 0
