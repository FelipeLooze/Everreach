"""Phase 14I — Local Economy.

Settlement wealth is a descriptive/liquidity signal, deliberately NEVER
a price multiplier — the spec is explicit about this, and nothing here
feeds into resolve_market_price or resolve_local_market_price (Phase
14B/14H). It answers different questions: how much money does a typical
merchant here realistically have, and does Gold circulate normally at
all — not "what does this item cost."

GOLD RARITY (the spec's own core principle) is expressed here as a
simple boolean per band, not a numeric multiplier: only WEALTHY
settlements treat Gold as unremarkable. Even there, Gold stays
substantial money — this function never claims otherwise.
"""

from sqlalchemy.orm import Session

from app.core.enums import SettlementWealthBand
from app.db.models.local_economy import LocationEconomy

_TYPICAL_MERCHANT_LIQUIDITY_BRONZE = {
    SettlementWealthBand.POOR: 200,
    SettlementWealthBand.MODEST: 1_000,
    SettlementWealthBand.PROSPEROUS: 5_000,
    SettlementWealthBand.WEALTHY: 20_000,
}


class LocalEconomyError(Exception):
    pass


def set_settlement_wealth(
    db: Session, campaign_id: str, location_id: str, wealth_band: SettlementWealthBand
) -> LocationEconomy:
    economy = db.query(LocationEconomy).filter(LocationEconomy.location_id == location_id).first()
    if economy is None:
        economy = LocationEconomy(campaign_id=campaign_id, location_id=location_id, wealth_band=wealth_band)
        db.add(economy)
    else:
        economy.wealth_band = wealth_band
    db.flush()
    return economy


def get_settlement_wealth(db: Session, location_id: str) -> SettlementWealthBand:
    """Absence of a row reads as MODEST — an unremarkable default, not an
    omniscient claim about a settlement nobody has described yet."""
    economy = db.query(LocationEconomy).filter(LocationEconomy.location_id == location_id).first()
    if economy is None:
        return SettlementWealthBand.MODEST
    return SettlementWealthBand(economy.wealth_band)


def typical_merchant_liquidity_bronze(wealth_band: SettlementWealthBand) -> int:
    """A rough guide for how much a typical shop's till might realistically
    hold here — a liquidity signal for content/world-building (e.g. Phase
    14G shop funding), not a formula applied automatically anywhere."""
    return _TYPICAL_MERCHANT_LIQUIDITY_BRONZE[wealth_band]


def gold_circulates_normally(wealth_band: SettlementWealthBand) -> bool:
    """Only WEALTHY settlements treat Gold as unremarkable — everywhere
    else, per the spec, even one Gold coin may draw attention (asked to
    break it, inspected, remembered). Gold remains substantial money even
    in a WEALTHY settlement; this only says whether seeing it is routine."""
    return wealth_band == SettlementWealthBand.WEALTHY
