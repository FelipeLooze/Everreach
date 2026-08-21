"""Phase 14M — Economic Events & World Simulation.

The reusable hook the spec asks for ("Bridge destroyed -> trade
disrupted -> imports fall -> specific prices may rise"): NOT a scripted
per-world-event-type outcome table. apply_economic_disruption is a
single, generic primitive any caller can invoke — a quest resolution, an
organization conflict (Phase 13L), a future travel-incident handler —
supplying exactly which items at which location are affected and by how
much. This module does not decide that a bridge collapsing means "grain
supply -30" — that judgment belongs to whoever actually knows a bridge
collapsed; this only performs the resulting, already-decided adjustment
through Phase 14H's real supply/demand primitives (never a parallel
mechanism).

Most of the spec's example economic events (WORKER_HIRED, WORKER_LEFT,
TRADE_COMPLETED, SHOP_RESTOCKED...) already exist under equivalent names
from earlier Phase 14 subphases (JOB_APPLICATION_RESOLVED,
JOB_EMPLOYMENT_ENDED, TRANSACTION_COMPLETED, SHOP_STOCKED) — not
duplicated here, per the spec's own "do not create every event
immediately."

"Economy does not need Logan" needed no new code here: every Phase 14
primitive (Job, Business, Shop, wallet, production) already operates on
arbitrary character/NPC/organization ids — nothing in this system has
ever required the protagonist specifically.
"""

from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.supply import LocalSupplyLevel
from app.game.economy.supply_demand import adjust_supply, get_or_create_supply_level
from app.services.event_log import log_event


class WorldEventEconomyError(Exception):
    pass


def apply_economic_disruption(
    db: Session,
    campaign_id: str,
    location_id: str,
    item_definition_ids: list[str],
    *,
    supply_delta: int,
    reason: str,
) -> list[LocalSupplyLevel]:
    """Adjusts local supply for every given item at one location by the
    same delta, in one logged disruption. supply_delta is negative for a
    shortage (a destroyed bridge cutting off imports), positive for a
    recovery or glut (a mine producing heavily) — see Phase 14H's own
    adjust_supply for the bounded clamping this reuses unchanged."""
    if not item_definition_ids:
        raise WorldEventEconomyError("Uma disrupção econômica precisa afetar ao menos um item.")

    levels = []
    for item_definition_id in item_definition_ids:
        level = get_or_create_supply_level(db, campaign_id, location_id, item_definition_id)
        adjust_supply(db, level, supply_delta, reason=reason)
        levels.append(level)

    log_event(
        db, campaign_id, EventType.ECONOMIC_DISRUPTION_APPLIED,
        actor_type="world",
        payload={
            "location_id": location_id,
            "item_definition_ids": item_definition_ids,
            "supply_delta": supply_delta,
            "reason": reason,
        },
    )
    return levels
