"""Phase 14C — Buying, Selling & Transactions.

The Narrator never moves an inventory or a balance — buy_item is the one
authoritative path: it verifies the seller actually owns the item,
resolves a price (explicit or the current market price, Phase 14B),
moves currency through the real wallet (Phase 14A, which already refuses
insufficient funds — no money is created), and moves the item through
the real Phase 10 ownership/location primitives (set_item_owner,
move_item_instance) — nothing here duplicates item or currency state.

BARTER (Phase 14C's own note): no barter engine is built here, but none
is needed for basic compatibility — an item-for-item trade is just two
ownership/location moves with no currency step, already expressible with
the same Phase 10 primitives this module already calls. A dedicated
barter valuation flow, if ever needed, belongs to a later subphase.

CHANGE-MAKING: this system does not model individual physical coins (see
Phase 14A) — money is a fungible Bronze balance, so a seller either has
enough total funds to make a purchase (as buyer) or does not; there is no
literal "doesn't have the right denominations" failure mode to simulate,
since nothing here ever required exact denominations in the first place.
"""

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, EventType, ItemLocationType, ItemOwnerType
from app.db.models.item import ItemInstance
from app.game.economy.pricing import resolve_market_price
from app.game.economy.wallet import get_or_create_holding, transfer
from app.game.items.service import move_item_instance, set_item_owner
from app.services.event_log import log_event

_ITEM_OWNER_TYPES = (CombatActorType.CHARACTER, CombatActorType.NPC)


class TransactionError(Exception):
    pass


def buy_item(
    db: Session,
    item: ItemInstance,
    *,
    buyer_type: CombatActorType,
    buyer_id: str,
    seller_type: CombatActorType,
    seller_id: str,
    price_bronze: int | None = None,
) -> int:
    """Transfers item ownership from seller to buyer and Bronze from
    buyer to seller, atomically. Returns the price actually paid.
    price_bronze overrides the resolved market price — e.g. for
    negotiated deals (Phase 14C's own NEGOTIATION note: this function
    doesn't decide the negotiated number, it only requires one exists)."""
    if buyer_type not in _ITEM_OWNER_TYPES or seller_type not in _ITEM_OWNER_TYPES:
        raise TransactionError(
            "Apenas personagens e NPCs podem possuir itens fisicamente (Fase 10)."
        )
    if item.owner_type != seller_type.value or item.owner_ref != seller_id:
        raise TransactionError("O vendedor não possui este item.")
    if buyer_type == seller_type and buyer_id == seller_id:
        raise TransactionError("Comprador e vendedor não podem ser a mesma pessoa.")

    price = price_bronze if price_bronze is not None else resolve_market_price(db, item)
    if price < 0:
        raise TransactionError("O preço de uma transação não pode ser negativo.")

    if price > 0:
        buyer_holding = get_or_create_holding(db, item.campaign_id, buyer_type, buyer_id)
        seller_holding = get_or_create_holding(db, item.campaign_id, seller_type, seller_id)
        transfer(
            db, buyer_holding, seller_holding, price,
            reason=f"Compra de {item.definition.name}",
        )

    set_item_owner(db, item, owner_type=ItemOwnerType(buyer_type.value), owner_ref=buyer_id)
    move_item_instance(
        db, item,
        location_type=ItemLocationType(buyer_type.value),
        location_ref=buyer_id,
    )

    log_event(
        db,
        item.campaign_id,
        EventType.TRANSACTION_COMPLETED,
        actor_type=buyer_type.lower(),
        actor_id=buyer_id,
        payload={
            "item_instance_id": item.id,
            "seller_type": seller_type,
            "seller_id": seller_id,
            "price_bronze": price,
        },
    )
    return price
