"""Phase 14H — Supply & Demand.

A restrained foundation, not a stock market: supply_index is clamped to
[10, 300] (never absurd extremes) and the resulting price multiplier is
separately clamped to [0.5, 2.0] — bounded modifiers, not exponential
chaos. One person buying three loaves does not spike bread prices 40%;
adjust_supply moves the index by an explicit, deliberate amount a caller
decides (a real disruption, a mine producing heavily), never an automatic
per-transaction reaction to every purchase.

resolve_local_market_price is the seam Phase 14B's resolve_market_price
was built for: quality/condition first (14B), then this location's
supply/demand on top. No LocalSupplyLevel row for a (location, item)
pair means "no known distortion" — plain resolve_market_price, unchanged.
"""

from sqlalchemy.orm import Session

from app.db.models.item import ItemInstance
from app.db.models.supply import LocalSupplyLevel
from app.game.economy.pricing import resolve_market_price
from app.game.time.clock import get_world_time
from app.services.event_log import log_event
from app.core.enums import EventType

BASELINE_SUPPLY_INDEX = 100
MIN_SUPPLY_INDEX = 10
MAX_SUPPLY_INDEX = 300
MIN_PRICE_MULTIPLIER = 0.5
MAX_PRICE_MULTIPLIER = 2.0


class SupplyError(Exception):
    pass


def get_or_create_supply_level(
    db: Session, campaign_id: str, location_id: str, item_definition_id: str
) -> LocalSupplyLevel:
    level = (
        db.query(LocalSupplyLevel)
        .filter(
            LocalSupplyLevel.location_id == location_id,
            LocalSupplyLevel.item_definition_id == item_definition_id,
        )
        .first()
    )
    if level is not None:
        return level
    world_minute = get_world_time(db, campaign_id).total_minutes()
    level = LocalSupplyLevel(
        campaign_id=campaign_id,
        location_id=location_id,
        item_definition_id=item_definition_id,
        supply_index=BASELINE_SUPPLY_INDEX,
        updated_world_minute=world_minute,
    )
    db.add(level)
    db.flush()
    return level


def adjust_supply(db: Session, level: LocalSupplyLevel, delta: int, *, reason: str) -> LocalSupplyLevel:
    if not reason.strip():
        raise SupplyError("Uma mudança de oferta precisa de um motivo explicável.")
    world_minute = get_world_time(db, level.campaign_id).total_minutes()
    previous = level.supply_index
    level.supply_index = max(MIN_SUPPLY_INDEX, min(MAX_SUPPLY_INDEX, level.supply_index + delta))
    level.updated_world_minute = world_minute
    db.flush()

    log_event(
        db, level.campaign_id, EventType.SUPPLY_CHANGED,
        actor_type="world",
        payload={
            "location_id": level.location_id,
            "item_definition_id": level.item_definition_id,
            "previous_supply_index": previous,
            "new_supply_index": level.supply_index,
            "reason": reason,
        },
        occurred_world_minute=world_minute,
    )
    return level


def supply_price_multiplier(supply_index: int) -> float:
    # supply_index 100 (baseline) -> 1.0. Lower supply -> higher
    # multiplier (shortage raises prices); higher supply -> lower
    # multiplier (surplus lowers prices).
    raw = BASELINE_SUPPLY_INDEX / max(supply_index, 1)
    return max(MIN_PRICE_MULTIPLIER, min(MAX_PRICE_MULTIPLIER, raw))


def resolve_local_market_price(db: Session, item_instance: ItemInstance, location_id: str) -> int:
    base_price = resolve_market_price(db, item_instance)
    if base_price == 0:
        return 0
    level = (
        db.query(LocalSupplyLevel)
        .filter(
            LocalSupplyLevel.location_id == location_id,
            LocalSupplyLevel.item_definition_id == item_instance.definition_id,
        )
        .first()
    )
    if level is None:
        return base_price
    multiplier = supply_price_multiplier(level.supply_index)
    return max(1, round(base_price * multiplier))
