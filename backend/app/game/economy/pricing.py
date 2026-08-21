"""Phase 14B — Prices & Valuation.

Items do NOT have one globally fixed universal price.
ItemDefinition.base_value_bronze (Phase 14B) is a reference value, not a
transaction price — resolve_market_price is where REFERENCE VALUE
becomes CURRENT MARKET PRICE, adjusted by quality/condition. Both are
consumed from Phase 10 directly (ItemInstance.quality,
app.game.items.durability.get_item_condition) — nothing here duplicates
quality/durability logic.

Deliberately NOT modeled yet (later subphases own these): settlement/
region, supply/demand, seller/buyer identity, reputation/relationship,
negotiation, taxation, war/disruption. resolve_market_price is the one
seam later subphases (14H Supply & Demand, 14I Local Economy) will
extend — the multiplier tables here are bounded, understandable, and
deliberately don't try to be an economic simulator.
"""

from sqlalchemy.orm import Session

from app.core.enums import ItemCondition, ItemQuality
from app.db.models.item import ItemDefinition, ItemInstance
from app.game.items.durability import get_item_condition

MIN_MARKET_PRICE_BRONZE = 1

_QUALITY_MULTIPLIER: dict[ItemQuality, float] = {
    ItemQuality.CRUDE: 0.5,
    ItemQuality.POOR: 0.75,
    ItemQuality.STANDARD: 1.0,
    ItemQuality.GOOD: 1.35,
    ItemQuality.EXCELLENT: 1.75,
    ItemQuality.MASTERWORK: 2.5,
}

_CONDITION_MULTIPLIER: dict[ItemCondition, float] = {
    ItemCondition.EXCELLENT: 1.0,
    ItemCondition.GOOD: 0.9,
    ItemCondition.WORN: 0.7,
    ItemCondition.DAMAGED: 0.45,
    ItemCondition.CRITICAL: 0.2,
    ItemCondition.BROKEN: 0.05,
}


class PricingError(Exception):
    pass


def set_item_base_value(db: Session, item_definition: ItemDefinition, base_value_bronze: int) -> ItemDefinition:
    if not isinstance(base_value_bronze, int) or isinstance(base_value_bronze, bool) or base_value_bronze < 0:
        raise PricingError("O valor de referência precisa ser um inteiro não negativo de Bronze.")
    item_definition.base_value_bronze = base_value_bronze
    db.flush()
    return item_definition


def resolve_market_price(db: Session, item_instance: ItemInstance) -> int:
    """The current, single-item market price in Bronze — REFERENCE VALUE
    adjusted for this specific instance's quality and condition (never
    mutating the item's own intrinsic base value). Raises if the item's
    definition has no established base value at all — a shop or narrator
    should treat that as "this isn't something with a known price," not
    silently charge 0."""
    definition = item_instance.definition
    if definition.base_value_bronze is None:
        raise PricingError(f"'{definition.name}' não tem valor de referência estabelecido.")

    if definition.base_value_bronze == 0:
        return 0

    multiplier = _QUALITY_MULTIPLIER.get(ItemQuality(item_instance.quality), 1.0)
    condition = get_item_condition(item_instance)
    if condition is not None:
        multiplier *= _CONDITION_MULTIPLIER.get(condition, 1.0)

    # A genuinely-priced item (base value > 0) never rounds down to free
    # just because quality/condition multipliers are harsh.
    price = round(definition.base_value_bronze * multiplier)
    return max(price, MIN_MARKET_PRICE_BRONZE)
