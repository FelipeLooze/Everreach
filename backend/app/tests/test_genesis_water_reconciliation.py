from copy import deepcopy
import pytest
from app.game.world.genesis.water_reconciliation.config import ReconciliationConfig, TransferIntent
from app.game.world.genesis.water_reconciliation.ledger import apply_batch
from app.game.world.genesis.water_reconciliation.admission import assess_geometry


def stock(amount, account="at:inlet"):
    return {"accounts": {account: amount}, "locations": {account: {"anchor_id": account}}, "opening_source": "analytic_test_only"}


def admitted(capacity=1000, key="analytic-channel", ocean=False):
    return {"status": "admitted", "reasons": [], "capacity_liters": capacity,
            "capacity_key": key, "ocean_export_authorized": ocean, "fixture_not_real_G1": True}


def intent(id="move", source=1, target=2, amount=50):
    return TransferIntent(transfer_id=id, source_node=source, target_node=target, source_account="at:inlet",
                          target_account="at:inlet", amount_liters=amount)


def test_exact_debit_credit_large_integers_and_no_mutation():
    amount = 10**35+7
    states = {1: stock(amount), 2: stock(0)}
    before = deepcopy(states)
    after, transfers, budgets = apply_batch(states, [intent(amount=amount)], {"move": admitted(amount)}, 0)
    assert states == before
    assert after[1]["accounts"]["at:inlet"] == 0 and after[2]["accounts"]["at:inlet"] == amount
    assert transfers[0]["applied_liters"] == amount
    assert all(b["residual_liters"] == 0 for b in budgets.values())


def test_confluence_order_and_same_period_receipts_not_respent():
    states = {1: stock(30), 2: stock(70), 3: stock(0), 4: stock(0)}
    moves = [intent("a", 1, 3, 30), intent("b", 2, 3, 70), intent("c", 3, 4, 100)]
    admissions = {m.transfer_id: admitted(key=m.transfer_id) for m in moves}
    first = apply_batch(states, moves, admissions, 1)
    assert first == apply_batch(states, list(reversed(moves)), admissions, 1)
    assert first[0][3]["accounts"]["at:inlet"] == 100
    assert first[0][4]["accounts"]["at:inlet"] == 0
    assert first[1][-1]["status"] == "pending"


def test_unlocated_pending_stock_is_never_mapped_or_lost():
    states = {1: stock(100), 2: stock(0)}
    states[1]["locations"] = {}
    after, rows, budgets = apply_batch(states, [intent()], {"move": admitted()}, 2)
    assert after == states and rows[0]["applied_liters"] == 0
    assert "source_localization_pending" in rows[0]["reasons"]
    assert budgets[1]["storage_delta_liters"] == 0


def test_source_and_shared_capacity_oversubscription_reject_entire_batch():
    states = {1: stock(100), 2: stock(0), 3: stock(0)}
    moves = [intent("a", 1, 2, 60), intent("b", 1, 3, 60)]
    with pytest.raises(ValueError, match="source stock"):
        apply_batch(states, moves, {"a": admitted(key="a"), "b": admitted(key="b")}, 0)
    with pytest.raises(ValueError, match="shared passage"):
        apply_batch(states, moves, {"a": admitted(100), "b": admitted(100)}, 0)
    assert states[1]["accounts"]["at:inlet"] == 100


def test_ocean_export_requires_connection_and_counts_as_output():
    move = intent(target=None, amount=20)
    with pytest.raises(ValueError, match="coastal proof"):
        apply_batch({1: stock(100)}, [move], {"move": admitted()}, 0)
    after, _, budget = apply_batch({1: stock(100)}, [move], {"move": admitted(ocean=True)}, 0)
    assert after[1]["accounts"]["at:inlet"] == 80
    assert budget[1]["ocean_export_liters"] == 20 and budget[1]["residual_liters"] == 0


def test_four_seasons_carry_one_stock_without_recrediting_climatology():
    states = {1: stock(100), 2: stock(0)}
    amounts, observed = [0, 30, 20, 0], []
    for season, amount in enumerate(amounts):
        states, rows, budgets = apply_batch(states, [intent(id=str(season), amount=amount)], {str(season): admitted()}, season)
        observed.append(rows[0]["applied_liters"])
        assert budgets[1]["new_precipitation_liters"] == 0
    assert observed == amounts
    assert states[1]["accounts"]["at:inlet"] == states[2]["accounts"]["at:inlet"] == 50


@pytest.mark.parametrize("kwargs", [{"water_version": True}, {"water_version": 1}, {"max_domains_per_revision": 0}])
def test_version_and_budgets_strict(kwargs):
    with pytest.raises(ValueError):
        ReconciliationConfig(**kwargs)
