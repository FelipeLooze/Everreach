"""Phase 14C — Buying, Selling & Transactions.

buy_item requires the seller to actually own the item and the buyer to
actually have enough funds — no money is created and no item moves
without both being real. Explicit price_bronze overrides the resolved
market price (e.g. for a negotiated deal).
"""

import pytest

from app.core.enums import CombatActorType
from app.game.character.service import create_character
from app.game.economy.currency import CurrencyError
from app.game.economy.pricing import PricingError, set_item_base_value
from app.game.economy.transactions import TransactionError, buy_item
from app.game.economy.wallet import deposit, get_or_create_holding
from app.game.inventory.service import add_item, get_or_create_item
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Transactions")
    region, village = seed_initial_region(db_session, campaign.id)
    seller = create_character(db_session, campaign.id, "Seller", region.id, village.id)
    buyer = create_character(db_session, campaign.id, "Buyer", region.id, village.id)
    db_session.flush()
    return campaign, seller, buyer


def test_buying_transfers_both_item_and_currency(db_session):
    campaign, seller, buyer = _setup(db_session)
    definition = get_or_create_item(db_session, "Pão")
    set_item_base_value(db_session, definition, 6)
    bread = add_item(db_session, seller.id, "Pão")
    buyer_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, buyer.id)
    deposit(db_session, buyer_holding, 20, reason="Saldo inicial.")

    price = buy_item(
        db_session, bread,
        buyer_type=CombatActorType.CHARACTER, buyer_id=buyer.id,
        seller_type=CombatActorType.CHARACTER, seller_id=seller.id,
    )

    assert price == 6
    assert bread.owner_type == "CHARACTER"
    assert bread.owner_ref == buyer.id
    seller_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, seller.id)
    assert seller_holding.amount_bronze == 6
    assert buyer_holding.amount_bronze == 14


def test_buying_without_enough_funds_fails_and_changes_nothing(db_session):
    campaign, seller, buyer = _setup(db_session)
    definition = get_or_create_item(db_session, "Espada Cara")
    set_item_base_value(db_session, definition, 500)
    sword = add_item(db_session, seller.id, "Espada Cara")

    with pytest.raises(CurrencyError):
        buy_item(
            db_session, sword,
            buyer_type=CombatActorType.CHARACTER, buyer_id=buyer.id,
            seller_type=CombatActorType.CHARACTER, seller_id=seller.id,
        )

    assert sword.owner_ref == seller.id


def test_cannot_buy_an_item_the_seller_does_not_own(db_session):
    campaign, seller, buyer = _setup(db_session)
    definition = get_or_create_item(db_session, "Machado")
    set_item_base_value(db_session, definition, 10)
    axe = add_item(db_session, seller.id, "Machado")

    with pytest.raises(TransactionError):
        buy_item(
            db_session, axe,
            buyer_type=CombatActorType.CHARACTER, buyer_id=buyer.id,
            seller_type=CombatActorType.CHARACTER, seller_id=buyer.id,
        )


def test_explicit_price_overrides_market_price(db_session):
    campaign, seller, buyer = _setup(db_session)
    definition = get_or_create_item(db_session, "Faca")
    set_item_base_value(db_session, definition, 20)
    knife = add_item(db_session, seller.id, "Faca")
    buyer_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, buyer.id)
    deposit(db_session, buyer_holding, 20, reason="Saldo inicial.")

    price = buy_item(
        db_session, knife,
        buyer_type=CombatActorType.CHARACTER, buyer_id=buyer.id,
        seller_type=CombatActorType.CHARACTER, seller_id=seller.id,
        price_bronze=12,
    )

    assert price == 12


def test_buying_an_item_with_no_price_and_no_override_raises(db_session):
    campaign, seller, buyer = _setup(db_session)
    unpriced = add_item(db_session, seller.id, "Item Sem Preço")

    with pytest.raises(PricingError):
        buy_item(
            db_session, unpriced,
            buyer_type=CombatActorType.CHARACTER, buyer_id=buyer.id,
            seller_type=CombatActorType.CHARACTER, seller_id=seller.id,
        )


def test_buyer_and_seller_cannot_be_the_same_person(db_session):
    campaign, seller, buyer = _setup(db_session)
    definition = get_or_create_item(db_session, "Item Qualquer")
    set_item_base_value(db_session, definition, 5)
    item = add_item(db_session, seller.id, "Item Qualquer")

    with pytest.raises(TransactionError):
        buy_item(
            db_session, item,
            buyer_type=CombatActorType.CHARACTER, buyer_id=seller.id,
            seller_type=CombatActorType.CHARACTER, seller_id=seller.id,
        )


def test_a_free_zero_price_transaction_still_moves_the_item(db_session):
    campaign, seller, buyer = _setup(db_session)
    definition = get_or_create_item(db_session, "Sucata")
    set_item_base_value(db_session, definition, 0)
    scrap = add_item(db_session, seller.id, "Sucata")

    price = buy_item(
        db_session, scrap,
        buyer_type=CombatActorType.CHARACTER, buyer_id=buyer.id,
        seller_type=CombatActorType.CHARACTER, seller_id=seller.id,
    )

    assert price == 0
    assert scrap.owner_ref == buyer.id
