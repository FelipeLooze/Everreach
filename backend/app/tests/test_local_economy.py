"""Phase 14I — Local Economy.

Settlement wealth is a descriptive/liquidity signal — never a price
multiplier. Absence of a row reads as MODEST, not an omniscient default
claim. Only WEALTHY settlements treat Gold as routine.
"""

from app.core.enums import SettlementWealthBand
from app.db.models.location import Location
from app.game.economy.local_economy import (
    get_settlement_wealth,
    gold_circulates_normally,
    set_settlement_wealth,
    typical_merchant_liquidity_bronze,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Local Economy")
    region, village = seed_initial_region(db_session, campaign.id)
    db_session.flush()
    return campaign, region, village


def test_unset_settlement_defaults_to_modest(db_session):
    # The starting village itself now always has an explicit wealth band
    # (Phase 15 follow-up — settlement parity), so this test needs a
    # location that genuinely has no LocationEconomy row at all: its own
    # forest geography feature never gets one.
    campaign, region, village = _setup(db_session)
    forest = db_session.query(Location).filter(
        Location.subregion_id == village.subregion_id, Location.type == "forest"
    ).one()

    assert get_settlement_wealth(db_session, forest.id) == SettlementWealthBand.MODEST


def test_setting_wealth_persists_and_is_readable(db_session):
    campaign, region, village = _setup(db_session)

    set_settlement_wealth(db_session, campaign.id, village.id, SettlementWealthBand.POOR)

    assert get_settlement_wealth(db_session, village.id) == SettlementWealthBand.POOR


def test_setting_wealth_twice_updates_the_same_row(db_session):
    campaign, region, village = _setup(db_session)

    set_settlement_wealth(db_session, campaign.id, village.id, SettlementWealthBand.POOR)
    set_settlement_wealth(db_session, campaign.id, village.id, SettlementWealthBand.WEALTHY)

    assert get_settlement_wealth(db_session, village.id) == SettlementWealthBand.WEALTHY


def test_wealthier_settlements_have_higher_typical_liquidity():
    poor = typical_merchant_liquidity_bronze(SettlementWealthBand.POOR)
    modest = typical_merchant_liquidity_bronze(SettlementWealthBand.MODEST)
    prosperous = typical_merchant_liquidity_bronze(SettlementWealthBand.PROSPEROUS)
    wealthy = typical_merchant_liquidity_bronze(SettlementWealthBand.WEALTHY)

    assert poor < modest < prosperous < wealthy


def test_only_wealthy_settlements_treat_gold_as_routine():
    assert gold_circulates_normally(SettlementWealthBand.POOR) is False
    assert gold_circulates_normally(SettlementWealthBand.MODEST) is False
    assert gold_circulates_normally(SettlementWealthBand.PROSPEROUS) is False
    assert gold_circulates_normally(SettlementWealthBand.WEALTHY) is True


def test_wealth_band_never_touches_item_pricing(db_session):
    # Deliberate architectural restraint: setting a settlement's wealth
    # must not silently change what resolve_market_price/
    # resolve_local_market_price return for any item.
    from app.game.character.service import create_character
    from app.game.economy.pricing import resolve_market_price, set_item_base_value
    from app.game.economy.supply_demand import resolve_local_market_price
    from app.game.inventory.service import add_item, get_or_create_item

    campaign, region, village = _setup(db_session)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    definition = get_or_create_item(db_session, "Pão")
    set_item_base_value(db_session, definition, 6)
    bread = add_item(db_session, character.id, "Pão")
    price_before = resolve_local_market_price(db_session, bread, village.id)

    set_settlement_wealth(db_session, campaign.id, village.id, SettlementWealthBand.WEALTHY)

    assert resolve_market_price(db_session, bread) == 6
    assert resolve_local_market_price(db_session, bread, village.id) == price_before
