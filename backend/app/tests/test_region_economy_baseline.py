"""Phase 15K — Regional Economy Baseline.

Every major settlement gets a wealth band (matching its own type — a
MAJOR_CITY is WEALTHY, an isolated hamlet is POOR) and, where it has one,
a real LocalSupplyLevel signal for its export good. Baseline facts only —
no simulated trade routes or years of pre-simulated economy.
"""

from app.core.enums import SettlementWealthBand
from app.db.models.local_economy import LocationEconomy
from app.db.models.settlement import Settlement
from app.db.models.supply import LocalSupplyLevel
from app.game.economy.supply_demand import BASELINE_SUPPLY_INDEX
from app.game.world.content_pools import EXPORT_GOOD_BY_SETTLEMENT_TYPE, WEALTH_BAND_BY_SETTLEMENT_TYPE
from app.game.world.seed import create_campaign, seed_initial_region


def test_every_major_settlement_gets_a_wealth_band(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    settlements = db_session.query(Settlement).all()
    for settlement in settlements:
        economy = (
            db_session.query(LocationEconomy)
            .filter(LocationEconomy.location_id == settlement.location_id)
            .one()
        )
        expected_band = WEALTH_BAND_BY_SETTLEMENT_TYPE[str(settlement.settlement_type)]
        assert economy.wealth_band == expected_band


def test_settlements_with_an_export_good_get_a_boosted_supply_level(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    settlements = db_session.query(Settlement).all()
    found_at_least_one_export = False
    for settlement in settlements:
        export_good = EXPORT_GOOD_BY_SETTLEMENT_TYPE[str(settlement.settlement_type)]
        if export_good is None:
            continue
        found_at_least_one_export = True
        levels = (
            db_session.query(LocalSupplyLevel)
            .filter(LocalSupplyLevel.location_id == settlement.location_id)
            .all()
        )
        assert len(levels) == 1
        assert levels[0].supply_index > BASELINE_SUPPLY_INDEX

    assert found_at_least_one_export


def test_major_city_is_wealthy(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    major_city = db_session.query(Settlement).filter(Settlement.settlement_type == "MAJOR_CITY").one()
    economy = (
        db_session.query(LocationEconomy)
        .filter(LocationEconomy.location_id == major_city.location_id)
        .one()
    )
    assert economy.wealth_band == SettlementWealthBand.WEALTHY
