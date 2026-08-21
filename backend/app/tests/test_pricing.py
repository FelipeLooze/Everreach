"""Phase 14B — Prices & Valuation.

base_value_bronze is a reference, never a fixed universal price —
resolve_market_price adjusts it per-instance by quality and condition,
consuming Phase 10's own ItemQuality/get_item_condition rather than
duplicating that logic. An item with no established value raises rather
than silently pricing at 0.
"""

import pytest

from app.core.enums import ItemQuality
from app.game.character.service import create_character
from app.game.economy.pricing import (
    PricingError,
    resolve_market_price,
    set_item_base_value,
)
from app.game.inventory.service import add_item, get_or_create_item
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Pricing")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, character


def test_item_without_a_base_value_has_no_market_price(db_session):
    campaign, character = _setup(db_session)
    item = add_item(db_session, character.id, "Pedra Comum")

    with pytest.raises(PricingError):
        resolve_market_price(db_session, item)


def test_standard_quality_intact_item_prices_at_base_value(db_session):
    campaign, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Machado de Ferro")
    set_item_base_value(db_session, definition, 40)
    item = add_item(db_session, character.id, "Machado de Ferro", quality=ItemQuality.STANDARD)

    assert resolve_market_price(db_session, item) == 40


def test_good_quality_prices_higher_than_standard(db_session):
    campaign, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Espada de Aço")
    set_item_base_value(db_session, definition, 100)
    standard = add_item(db_session, character.id, "Espada de Aço", quality=ItemQuality.STANDARD)
    good = add_item(db_session, character.id, "Espada de Aço", quality=ItemQuality.GOOD)

    assert resolve_market_price(db_session, good) > resolve_market_price(db_session, standard)


def test_damaged_condition_prices_lower_than_excellent(db_session):
    campaign, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Machado Desgastado")
    set_item_base_value(db_session, definition, 40)
    item = add_item(db_session, character.id, "Machado Desgastado")
    item.durability_current = 95.0
    item.durability_max = 100.0
    excellent_price = resolve_market_price(db_session, item)

    item.durability_current = 30.0  # ratio 0.30 -> DAMAGED
    damaged_price = resolve_market_price(db_session, item)

    assert damaged_price < excellent_price


def test_a_positive_base_value_never_rounds_down_to_free(db_session):
    campaign, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Prego Enferrujado")
    set_item_base_value(db_session, definition, 1)
    item = add_item(db_session, character.id, "Prego Enferrujado", quality=ItemQuality.CRUDE)
    item.durability_current = 1.0
    item.durability_max = 100.0  # ratio 0.01 -> BROKEN territory, harsh multiplier

    assert resolve_market_price(db_session, item) >= 1


def test_a_base_value_of_zero_stays_zero(db_session):
    campaign, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Sucata Sem Valor")
    set_item_base_value(db_session, definition, 0)
    item = add_item(db_session, character.id, "Sucata Sem Valor", quality=ItemQuality.MASTERWORK)

    assert resolve_market_price(db_session, item) == 0


def test_set_item_base_value_rejects_negative_amounts(db_session):
    campaign, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Item Qualquer")

    with pytest.raises(PricingError):
        set_item_base_value(db_session, definition, -5)
