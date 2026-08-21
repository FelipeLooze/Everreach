"""Phase 14A — Currency Foundation.

100 Bronze = 1 Silver, 100 Silver = 1 Gold, fixed. Bronze (the canonical
smallest unit) is always an integer — there is no fractional Bronze, and
money is never represented as a Python float anywhere in this system.
Money is never one row per coin: CurrencyHolding accumulates per
(owner, container) pair, and container_item_instance_id lets it reuse a
real Phase 10 container (a chest) instead of only living "on the
person," without ever creating a coin-per-row explosion.
"""

import pytest

from app.core.enums import CombatActorType
from app.game.character.service import create_character
from app.game.economy.currency import (
    BRONZE_PER_GOLD,
    BRONZE_PER_SILVER,
    CurrencyError,
    from_denominations,
    to_denominations,
)
from app.game.economy.wallet import (
    deposit,
    get_or_create_holding,
    total_carried_by_owner,
    transfer,
    withdraw,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Currency Foundation")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, character


# --- Pure conversion math ---------------------------------------------


def test_zero_converts_to_all_zero_denominations():
    assert to_denominations(0) == to_denominations(0)
    result = to_denominations(0)
    assert (result.gold, result.silver, result.bronze) == (0, 0, 0)


def test_99_bronze_stays_bronze_only():
    result = to_denominations(99)
    assert (result.gold, result.silver, result.bronze) == (0, 0, 99)


def test_100_bronze_becomes_exactly_one_silver():
    result = to_denominations(100)
    assert (result.gold, result.silver, result.bronze) == (0, 1, 0)


def test_99_silver_worth_of_bronze_stays_silver_only():
    result = to_denominations(99 * BRONZE_PER_SILVER)
    assert (result.gold, result.silver, result.bronze) == (0, 99, 0)


def test_100_silver_worth_of_bronze_becomes_exactly_one_gold():
    result = to_denominations(100 * BRONZE_PER_SILVER)
    assert (result.gold, result.silver, result.bronze) == (1, 0, 0)


def test_the_worked_example_from_the_spec():
    # 25,430 Bronze -> 2 Gold, 54 Silver, 30 Bronze
    result = to_denominations(25_430)
    assert (result.gold, result.silver, result.bronze) == (2, 54, 30)


def test_large_value_round_trips():
    amount = 123_456_789
    result = to_denominations(amount)
    assert from_denominations(gold=result.gold, silver=result.silver, bronze=result.bronze) == amount


def test_negative_bronze_is_explicitly_rejected():
    with pytest.raises(CurrencyError):
        to_denominations(-1)


def test_negative_denomination_component_is_explicitly_rejected():
    with pytest.raises(CurrencyError):
        from_denominations(gold=-1)


def test_non_integer_amount_is_rejected():
    with pytest.raises(CurrencyError):
        to_denominations(10.5)  # type: ignore[arg-type]


def test_from_denominations_matches_the_fixed_conversion_rate():
    assert from_denominations(gold=1) == BRONZE_PER_GOLD
    assert from_denominations(silver=1) == BRONZE_PER_SILVER
    assert from_denominations(gold=1, silver=1, bronze=1) == BRONZE_PER_GOLD + BRONZE_PER_SILVER + 1


# --- Physical holdings ---------------------------------------------------


def test_a_character_starts_with_no_holding_until_one_is_created(db_session):
    campaign, character = _setup(db_session)

    assert total_carried_by_owner(db_session, CombatActorType.CHARACTER, character.id) == 0


def test_deposit_and_withdraw_are_integer_only(db_session):
    campaign, character = _setup(db_session)
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)

    deposit(db_session, holding, 47, reason="Pagamento por um trabalho.")
    withdraw(db_session, holding, 12, reason="Compra de pão.")

    assert holding.amount_bronze == 35


def test_cannot_withdraw_more_than_is_held(db_session):
    campaign, character = _setup(db_session)
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    deposit(db_session, holding, 10, reason="Pagamento.")

    with pytest.raises(CurrencyError):
        withdraw(db_session, holding, 20, reason="Compra cara demais.")


def test_get_or_create_holding_is_idempotent_per_owner_and_container(db_session):
    campaign, character = _setup(db_session)

    first = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    second = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)

    assert first.id == second.id


def test_money_in_a_container_is_separate_from_money_carried_personally(db_session):
    from app.game.inventory.service import add_item, get_or_create_item

    campaign, character = _setup(db_session)
    get_or_create_item(db_session, "Baú de Madeira", "CONTAINER", base_weight=10)
    chest = add_item(db_session, character.id, "Baú de Madeira")

    personal = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    in_chest = get_or_create_holding(
        db_session, campaign.id, CombatActorType.CHARACTER, character.id,
        container_item_instance_id=chest.id,
    )

    deposit(db_session, personal, 30, reason="Dinheiro no bolso.")
    deposit(db_session, in_chest, 1000, reason="Economias guardadas no baú.")

    assert personal.id != in_chest.id
    assert personal.amount_bronze == 30
    assert in_chest.amount_bronze == 1000
    assert total_carried_by_owner(db_session, CombatActorType.CHARACTER, character.id) == 1030


def test_transfer_moves_value_without_creating_or_destroying_it(db_session):
    campaign, character = _setup(db_session)
    other_campaign_character = create_character(
        db_session, campaign.id, "Merchant",
        character.region_id, character.location_id,
    )
    payer = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    payee = get_or_create_holding(
        db_session, campaign.id, CombatActorType.CHARACTER, other_campaign_character.id
    )
    deposit(db_session, payer, 50, reason="Saldo inicial.")

    transfer(db_session, payer, payee, 8, reason="Pagamento pelo pão.")

    assert payer.amount_bronze == 42
    assert payee.amount_bronze == 8


def test_cannot_transfer_more_than_is_held(db_session):
    campaign, character = _setup(db_session)
    other = create_character(
        db_session, campaign.id, "Merchant", character.region_id, character.location_id,
    )
    payer = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    payee = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, other.id)
    deposit(db_session, payer, 5, reason="Saldo inicial.")

    with pytest.raises(CurrencyError):
        transfer(db_session, payer, payee, 10, reason="Pagamento maior que o saldo.")


def test_cannot_transfer_to_the_same_holding(db_session):
    campaign, character = _setup(db_session)
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    deposit(db_session, holding, 10, reason="Saldo inicial.")

    with pytest.raises(CurrencyError):
        transfer(db_session, holding, holding, 5, reason="Transferência inválida.")


def test_deposit_requires_a_positive_integer_amount(db_session):
    campaign, character = _setup(db_session)
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)

    with pytest.raises(CurrencyError):
        deposit(db_session, holding, 0, reason="Valor zero.")
    with pytest.raises(CurrencyError):
        deposit(db_session, holding, -5, reason="Valor negativo.")


def test_holding_requires_an_explainable_reason(db_session):
    campaign, character = _setup(db_session)
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)

    with pytest.raises(CurrencyError):
        deposit(db_session, holding, 10, reason="   ")
