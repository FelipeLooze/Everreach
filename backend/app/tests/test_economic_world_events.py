"""Phase 14M — Economic Events & World Simulation.

apply_economic_disruption is a generic, reusable hook — it never decides
that "a bridge collapsing" means a specific supply change; it only
performs the adjustment a caller already decided, through the real Phase
14H supply/demand primitives (bounded clamping included, unchanged).
"""

import pytest

from app.game.character.service import create_character
from app.game.economy.pricing import set_item_base_value
from app.game.economy.supply_demand import resolve_local_market_price
from app.game.economy.world_events import WorldEventEconomyError, apply_economic_disruption
from app.game.inventory.service import add_item, get_or_create_item
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Economic World Events")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def test_a_disruption_raises_local_prices_for_the_affected_items(db_session):
    # Not "Grão"/"Ferramentas": those are real settlement export goods now
    # (Phase 15K/15 follow-up) and may already carry a boosted local
    # supply at the starting village, which would understate this test's
    # own disruption delta. A fresh, uninvolved item keeps the assertion
    # about apply_economic_disruption itself, not about export baselines.
    campaign, region, village, character = _setup(db_session)
    spice = get_or_create_item(db_session, "Especiarias Raras")
    set_item_base_value(db_session, spice, 10)
    spice_stack = add_item(db_session, character.id, "Especiarias Raras")

    apply_economic_disruption(
        db_session, campaign.id, village.id, [spice.id],
        supply_delta=-60, reason="Ponte destruída corta a rota de importação.",
    )

    assert resolve_local_market_price(db_session, spice_stack, village.id) > 10


def test_a_disruption_affects_multiple_items_at_once(db_session):
    campaign, region, village, character = _setup(db_session)
    spice = get_or_create_item(db_session, "Especiarias Raras")
    set_item_base_value(db_session, spice, 10)
    silk = get_or_create_item(db_session, "Seda Fina")
    set_item_base_value(db_session, silk, 30)
    spice_stack = add_item(db_session, character.id, "Especiarias Raras")
    silk_stack = add_item(db_session, character.id, "Seda Fina")

    apply_economic_disruption(
        db_session, campaign.id, village.id, [spice.id, silk.id],
        supply_delta=-60, reason="Estrada bloqueada.",
    )

    assert resolve_local_market_price(db_session, spice_stack, village.id) > 10
    assert resolve_local_market_price(db_session, silk_stack, village.id) > 30


def test_a_positive_disruption_can_lower_prices(db_session):
    campaign, region, village, character = _setup(db_session)
    iron = get_or_create_item(db_session, "Ferro")
    set_item_base_value(db_session, iron, 20)
    iron_stack = add_item(db_session, character.id, "Ferro")

    apply_economic_disruption(
        db_session, campaign.id, village.id, [iron.id],
        supply_delta=100, reason="Mina reaberta produz intensamente.",
    )

    assert resolve_local_market_price(db_session, iron_stack, village.id) < 20


def test_disruption_requires_at_least_one_item(db_session):
    campaign, region, village, character = _setup(db_session)

    with pytest.raises(WorldEventEconomyError):
        apply_economic_disruption(
            db_session, campaign.id, village.id, [], supply_delta=-10, reason="Motivo.",
        )


def test_disruption_never_affects_an_unrelated_item(db_session):
    campaign, region, village, character = _setup(db_session)
    grain = get_or_create_item(db_session, "Grão")
    set_item_base_value(db_session, grain, 10)
    bread = get_or_create_item(db_session, "Pão")
    set_item_base_value(db_session, bread, 6)
    bread_stack = add_item(db_session, character.id, "Pão")

    apply_economic_disruption(
        db_session, campaign.id, village.id, [grain.id],
        supply_delta=-60, reason="Falha na colheita de grãos.",
    )

    assert resolve_local_market_price(db_session, bread_stack, village.id) == 6
