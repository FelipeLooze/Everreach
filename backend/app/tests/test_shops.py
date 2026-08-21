"""Phase 14G — Shops & Merchants.

A shop's stock is real Phase 10 inventory owned by its operator, not a
separate item universe. Its till is finite and separate from the
operator's personal money — a shop can refuse to buy something it can't
afford, and only buys item types it declared interest in.
"""

import pytest

from app.core.enums import CombatActorType, ItemType
from app.game.character.service import create_character
from app.game.economy.pricing import set_item_base_value
from app.game.economy.shops import (
    ShopError,
    buy_from_shop,
    create_shop,
    deposit_till,
    list_shop_stock,
    sell_to_shop,
    stock_item,
    unstock_item,
    withdraw_till,
)
from app.game.economy.wallet import deposit, get_or_create_holding
from app.game.inventory.service import add_item, get_or_create_item
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Shops")
    region, village = seed_initial_region(db_session, campaign.id)
    operator = create_character(db_session, campaign.id, "Merchant", region.id, village.id)
    customer = create_character(db_session, campaign.id, "Customer", region.id, village.id)
    shop = create_shop(
        db_session, campaign.id, "Ferraria de Cardal", CombatActorType.CHARACTER, operator.id,
        location_id=village.id, accepted_item_types=(ItemType.WEAPON, ItemType.TOOL),
    )
    db_session.flush()
    return campaign, region, village, operator, customer, shop


def test_stocking_an_item_the_operator_does_not_own_fails(db_session):
    campaign, region, village, operator, customer, shop = _setup(db_session)
    sword = add_item(db_session, customer.id, "Espada")

    with pytest.raises(ShopError):
        stock_item(db_session, shop, sword)


def test_customer_can_buy_stocked_item_and_till_receives_payment(db_session):
    campaign, region, village, operator, customer, shop = _setup(db_session)
    definition = get_or_create_item(db_session, "Machado de Ferro", "TOOL")
    set_item_base_value(db_session, definition, 40)
    axe = add_item(db_session, operator.id, "Machado de Ferro")
    listing = stock_item(db_session, shop, axe)
    customer_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, customer.id)
    deposit(db_session, customer_holding, 100, reason="Saldo inicial.")

    price = buy_from_shop(db_session, shop, listing, buyer_type=CombatActorType.CHARACTER, buyer_id=customer.id)

    assert price == 40
    assert shop.till_bronze == 40
    assert customer_holding.amount_bronze == 60
    assert axe.owner_ref == customer.id
    assert list_shop_stock(db_session, shop.id) == []


def test_buying_without_enough_funds_fails(db_session):
    campaign, region, village, operator, customer, shop = _setup(db_session)
    definition = get_or_create_item(db_session, "Machado Caro", "TOOL")
    set_item_base_value(db_session, definition, 500)
    axe = add_item(db_session, operator.id, "Machado Caro")
    listing = stock_item(db_session, shop, axe)

    from app.game.economy.currency import CurrencyError

    with pytest.raises(CurrencyError):
        buy_from_shop(db_session, shop, listing, buyer_type=CombatActorType.CHARACTER, buyer_id=customer.id)


def test_shop_refuses_to_buy_an_item_outside_its_specialization(db_session):
    campaign, region, village, operator, customer, shop = _setup(db_session)
    deposit_till(db_session, shop, 100, reason="Caixa inicial.")
    definition = get_or_create_item(db_session, "Pão", "CONSUMABLE")
    set_item_base_value(db_session, definition, 5)
    bread = add_item(db_session, customer.id, "Pão")

    with pytest.raises(ShopError):
        sell_to_shop(db_session, shop, bread, seller_type=CombatActorType.CHARACTER, seller_id=customer.id)


def test_shop_refuses_to_buy_what_it_cannot_afford(db_session):
    campaign, region, village, operator, customer, shop = _setup(db_session)
    definition = get_or_create_item(db_session, "Espada Cara", "WEAPON")
    set_item_base_value(db_session, definition, 200)
    sword = add_item(db_session, customer.id, "Espada Cara")

    with pytest.raises(ShopError):
        sell_to_shop(db_session, shop, sword, seller_type=CombatActorType.CHARACTER, seller_id=customer.id)

    assert sword.owner_ref == customer.id


def test_shop_buys_an_accepted_item_it_can_afford(db_session):
    campaign, region, village, operator, customer, shop = _setup(db_session)
    deposit_till(db_session, shop, 100, reason="Caixa inicial.")
    definition = get_or_create_item(db_session, "Espada Usada", "WEAPON")
    set_item_base_value(db_session, definition, 30)
    sword = add_item(db_session, customer.id, "Espada Usada")

    price = sell_to_shop(db_session, shop, sword, seller_type=CombatActorType.CHARACTER, seller_id=customer.id)

    assert price == 30
    assert shop.till_bronze == 70
    assert sword.owner_ref == operator.id
    seller_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, customer.id)
    assert seller_holding.amount_bronze == 30


def test_unstocking_removes_the_listing_but_keeps_the_item(db_session):
    campaign, region, village, operator, customer, shop = _setup(db_session)
    definition = get_or_create_item(db_session, "Picareta", "TOOL")
    set_item_base_value(db_session, definition, 15)
    pick = add_item(db_session, operator.id, "Picareta")
    listing = stock_item(db_session, shop, pick)

    unstock_item(db_session, shop, listing)

    assert list_shop_stock(db_session, shop.id) == []
    assert pick.owner_ref == operator.id


def test_withdrawing_more_than_the_till_holds_fails(db_session):
    campaign, region, village, operator, customer, shop = _setup(db_session)
    deposit_till(db_session, shop, 10, reason="Caixa inicial.")

    with pytest.raises(ShopError):
        withdraw_till(db_session, shop, 50, reason="Compra grande demais.")
