"""Phase 14F — Production.

labor + tools + materials + time + capability -> goods. Reuses Phase 10
items directly (add_item/remove_item) — no parallel crafting/inventory
system. Production is real: consuming inputs the producer doesn't have
raises (remove_item, Phase 14F's own addition to Phase 10, since an
add_item counterpart existed but remove_item didn't) — there is no
infinite restocking, and a shop cannot magically refill from nothing.

Batch/time abstraction (Phase 14F's own principle: don't simulate every
grain of flour): produce_goods is a single call representing one
completed batch — a baker's morning shift, not each loaf individually.
Deciding when/how often it's called (a work shift, a Job's payment
cycle) is not this function's job.

Production does NOT directly grant Profession XP (the spec is explicit
about this) — it only performs the authoritative item exchange; a real
qualifying action elsewhere would be what emits a ProgressionOutcome for
Phase 8 to consume, exactly like every other Phase 11-era system in this
project. Character-scoped only for now: add_item (Phase 10) itself has
no NPC-held counterpart, so NPC-run production (a baker NPC) is not yet
possible through this function — a pre-existing Phase 10 gap, not
something this subphase silently works around.
"""

from sqlalchemy.orm import Session

from app.core.enums import EventType, ItemLocationType, ItemQuality
from app.db.models.character import Character
from app.db.models.item import Item, ItemInstance
from app.game.inventory.service import add_item, remove_item
from app.services.event_log import log_event


class ProductionError(Exception):
    pass


def _require_available(db: Session, character_id: str, item_name: str, quantity: int) -> None:
    definition = db.query(Item).filter(Item.name == item_name).first()
    available = (
        sum(
            stack.quantity
            for stack in db.query(ItemInstance).filter(
                ItemInstance.definition_id == definition.id,
                ItemInstance.location_type == ItemLocationType.CHARACTER.value,
                ItemInstance.location_ref == character_id,
            )
        )
        if definition is not None
        else 0
    )
    if available < quantity:
        raise ProductionError(
            f"Insumo insuficiente: '{item_name}' ({available} disponível, {quantity} necessário)."
        )


def produce_goods(
    db: Session,
    campaign_id: str,
    producer_character_id: str,
    *,
    inputs: list[tuple[str, int]],
    outputs: list[tuple[str, int]],
    output_quality: ItemQuality = ItemQuality.STANDARD,
) -> list[ItemInstance]:
    if not outputs:
        raise ProductionError("Uma produção precisa gerar ao menos um bem.")
    character = db.get(Character, producer_character_id)
    if character is None or character.campaign_id != campaign_id:
        raise ProductionError("Produtor desconhecido nesta campanha.")

    # Validate every input is available BEFORE consuming any of them — a
    # production batch either fully happens or doesn't touch inventory at
    # all, never partially consumes some inputs and then fails on a later
    # one. Aggregated by name first so a repeated ingredient in the list
    # is checked against its true total requirement, not independently.
    required_totals: dict[str, int] = {}
    for item_name, quantity in inputs:
        required_totals[item_name] = required_totals.get(item_name, 0) + quantity
    for item_name, total_quantity in required_totals.items():
        _require_available(db, producer_character_id, item_name, total_quantity)
    for item_name, quantity in inputs:
        remove_item(db, producer_character_id, item_name, quantity)

    produced = [
        add_item(db, producer_character_id, item_name, quantity, quality=output_quality)
        for item_name, quantity in outputs
    ]

    log_event(
        db,
        campaign_id,
        EventType.PRODUCTION_COMPLETED,
        actor_type="character",
        actor_id=producer_character_id,
        payload={
            "inputs": [{"item_name": name, "quantity": qty} for name, qty in inputs],
            "outputs": [{"item_name": name, "quantity": qty} for name, qty in outputs],
        },
    )
    return produced
