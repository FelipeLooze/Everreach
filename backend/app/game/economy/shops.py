"""Phase 14G — Shops & Merchants.

A shop is a real world business, not a magical storefront menu. Its
stock is authoritative Phase 10 inventory owned by the operator
(ShopListing only marks which of the operator's items are currently for
sale, not personal belongings) — buying/selling here reuses
set_item_owner/move_item_instance directly, the same Phase 10 primitives
Phase 14C's buy_item uses, since a shop's till (not the operator's
personal wallet) is what actually receives/pays money, which Phase 14C's
person-to-person buy_item doesn't model.

SHOP MONEY is finite: sell_to_shop refuses a purchase the till can't
afford — a merchant simply cannot buy everything a customer offers.
SHOP SPECIALIZATION: sell_to_shop refuses an item type the shop hasn't
declared interest in (accepted_item_types) — a bakery does not buy a
customer's damaged sword.
"""

import json

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    EventType,
    ItemLocationType,
    ItemOwnerType,
    ItemType,
    ShopStatus,
)
from app.db.models.item import ItemInstance
from app.db.models.shop import Shop, ShopListing
from app.game.economy.pricing import resolve_market_price
from app.game.economy.wallet import get_or_create_holding
from app.game.economy.wallet import withdraw as wallet_withdraw
from app.game.economy.wallet import deposit as wallet_deposit
from app.game.items.service import move_item_instance, set_item_owner
from app.services.event_log import log_event

_SHOP_OPERATOR_TYPES = (CombatActorType.CHARACTER, CombatActorType.NPC)


class ShopError(Exception):
    pass


def create_shop(
    db: Session,
    campaign_id: str,
    name: str,
    operator_type: CombatActorType,
    operator_id: str,
    *,
    location_id: str,
    accepted_item_types: tuple[ItemType, ...] = (),
) -> Shop:
    if operator_type not in _SHOP_OPERATOR_TYPES:
        raise ShopError("O operador de uma loja precisa ser um personagem ou NPC (Fase 10).")
    if not name.strip():
        raise ShopError("Uma loja precisa de um nome.")
    shop = Shop(
        campaign_id=campaign_id,
        name=name,
        operator_type=operator_type,
        operator_id=operator_id,
        location_id=location_id,
        status=ShopStatus.OPEN,
        till_bronze=0,
        accepted_item_types_json=json.dumps([item_type.value for item_type in accepted_item_types]),
    )
    db.add(shop)
    db.flush()
    return shop


def deposit_till(db: Session, shop: Shop, amount_bronze: int, *, reason: str) -> Shop:
    return _change_till(db, shop, amount_bronze, reason=reason)


def withdraw_till(db: Session, shop: Shop, amount_bronze: int, *, reason: str) -> Shop:
    if amount_bronze > shop.till_bronze:
        raise ShopError(
            f"'{shop.name}' não tem fundos suficientes no caixa "
            f"({shop.till_bronze} bronze disponíveis, {amount_bronze} solicitados)."
        )
    return _change_till(db, shop, -amount_bronze, reason=reason)


def _change_till(db: Session, shop: Shop, delta: int, *, reason: str) -> Shop:
    if not reason.strip():
        raise ShopError("Uma mudança no caixa da loja precisa de um motivo explicável.")
    shop.till_bronze += delta
    db.flush()
    log_event(
        db, shop.campaign_id, EventType.SHOP_TILL_CHANGED,
        actor_type="shop", actor_id=shop.id,
        payload={"delta": delta, "reason": reason, "new_balance": shop.till_bronze},
    )
    return shop


def stock_item(
    db: Session, shop: Shop, item: ItemInstance, *, asking_price_bronze: int | None = None
) -> ShopListing:
    if item.owner_type != shop.operator_type or item.owner_ref != shop.operator_id:
        raise ShopError("A loja só pode vender itens que seu operador realmente possui.")
    existing = db.query(ShopListing).filter(ShopListing.item_instance_id == item.id).first()
    if existing is not None:
        return existing
    listing = ShopListing(shop_id=shop.id, item_instance_id=item.id, asking_price_bronze=asking_price_bronze)
    db.add(listing)
    db.flush()
    log_event(
        db, shop.campaign_id, EventType.SHOP_STOCKED,
        actor_type="shop", actor_id=shop.id,
        payload={"item_instance_id": item.id, "asking_price_bronze": asking_price_bronze},
    )
    return listing


def unstock_item(db: Session, shop: Shop, listing: ShopListing) -> None:
    db.delete(listing)
    db.flush()
    log_event(
        db, shop.campaign_id, EventType.SHOP_UNSTOCKED,
        actor_type="shop", actor_id=shop.id,
        payload={"item_instance_id": listing.item_instance_id},
    )


def list_shop_stock(db: Session, shop_id: str) -> list[ShopListing]:
    return db.query(ShopListing).filter(ShopListing.shop_id == shop_id).all()


def buy_from_shop(
    db: Session, shop: Shop, listing: ShopListing, *, buyer_type: CombatActorType, buyer_id: str
) -> int:
    """A customer buying shop stock — payment goes into the shop's own
    till, not the operator's personal wallet."""
    if shop.status != ShopStatus.OPEN:
        raise ShopError(f"'{shop.name}' não está aberta no momento.")
    item = db.get(ItemInstance, listing.item_instance_id)
    if item is None:
        raise ShopError("Este item não existe mais.")
    price = listing.asking_price_bronze if listing.asking_price_bronze is not None else resolve_market_price(db, item)

    buyer_holding = get_or_create_holding(db, shop.campaign_id, buyer_type, buyer_id)
    if price > 0:
        wallet_withdraw(db, buyer_holding, price, reason=f"Compra de {item.definition.name} em {shop.name}.")
        shop.till_bronze += price
        db.flush()

    set_item_owner(db, item, owner_type=ItemOwnerType(buyer_type.value), owner_ref=buyer_id)
    move_item_instance(db, item, location_type=ItemLocationType(buyer_type.value), location_ref=buyer_id)
    db.delete(listing)
    db.flush()

    log_event(
        db, shop.campaign_id, EventType.TRANSACTION_COMPLETED,
        actor_type=buyer_type.lower(), actor_id=buyer_id,
        payload={"shop_id": shop.id, "item_instance_id": item.id, "price_bronze": price},
    )
    return price


def sell_to_shop(
    db: Session,
    shop: Shop,
    item: ItemInstance,
    *,
    seller_type: CombatActorType,
    seller_id: str,
    price_bronze: int | None = None,
) -> int:
    """A customer selling an item to the shop — the sold item becomes the
    operator's inventory (not automatically re-listed for resale; see
    stock_item for that separate decision)."""
    if shop.status != ShopStatus.OPEN:
        raise ShopError(f"'{shop.name}' não está aberta no momento.")
    if item.owner_type != seller_type.value or item.owner_ref != seller_id:
        raise ShopError("Você não possui este item.")

    accepted = json.loads(shop.accepted_item_types_json)
    if accepted and item.definition.type not in accepted:
        raise ShopError(f"'{shop.name}' não compra itens do tipo {item.definition.type}.")

    price = price_bronze if price_bronze is not None else resolve_market_price(db, item)
    if price > shop.till_bronze:
        raise ShopError(
            f"'{shop.name}' não tem fundos suficientes pra comprar isso "
            f"({shop.till_bronze} bronze disponíveis, {price} solicitados)."
        )

    if price > 0:
        seller_holding = get_or_create_holding(db, shop.campaign_id, seller_type, seller_id)
        shop.till_bronze -= price
        wallet_deposit(db, seller_holding, price, reason=f"Venda de {item.definition.name} para {shop.name}.")

    set_item_owner(db, item, owner_type=ItemOwnerType(shop.operator_type), owner_ref=shop.operator_id)
    move_item_instance(
        db, item, location_type=ItemLocationType(shop.operator_type), location_ref=shop.operator_id
    )
    db.flush()

    log_event(
        db, shop.campaign_id, EventType.TRANSACTION_COMPLETED,
        actor_type=seller_type.lower(), actor_id=seller_id,
        payload={"shop_id": shop.id, "item_instance_id": item.id, "price_bronze": price},
    )
    return price
