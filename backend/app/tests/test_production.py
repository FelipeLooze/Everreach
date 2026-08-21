"""Phase 14F — Production.

Production is real: consuming inputs a producer doesn't have raises and
touches nothing, never partially consumes some inputs and produces
nothing. Reuses Phase 10 items directly (add_item/remove_item) — no
parallel crafting/inventory system.
"""

import pytest

from app.game.character.service import create_character
from app.game.economy.production import ProductionError, produce_goods
from app.game.inventory.service import add_item, list_inventory, remove_item
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Production")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, character


# --- remove_item (Phase 10 gap this subphase fills) -----------------------


def test_remove_item_decrements_a_stack(db_session):
    campaign, character = _setup(db_session)
    add_item(db_session, character.id, "Farinha", 10)

    remove_item(db_session, character.id, "Farinha", 4)

    remaining = [i for i in list_inventory(db_session, character.id) if i.definition.name == "Farinha"]
    assert remaining[0].quantity == 6


def test_remove_item_deletes_the_stack_when_it_reaches_zero(db_session):
    campaign, character = _setup(db_session)
    add_item(db_session, character.id, "Farinha", 5)

    remove_item(db_session, character.id, "Farinha", 5)

    assert list_inventory(db_session, character.id) == []


def test_remove_item_raises_when_insufficient(db_session):
    campaign, character = _setup(db_session)
    add_item(db_session, character.id, "Farinha", 2)

    with pytest.raises(ValueError):
        remove_item(db_session, character.id, "Farinha", 5)

    # Nothing was consumed by the failed attempt.
    remaining = [i for i in list_inventory(db_session, character.id) if i.definition.name == "Farinha"]
    assert remaining[0].quantity == 2


def test_remove_item_raises_for_an_unknown_item(db_session):
    campaign, character = _setup(db_session)

    with pytest.raises(ValueError):
        remove_item(db_session, character.id, "Item Inexistente", 1)


# --- produce_goods ----------------------------------------------------------


def test_production_consumes_inputs_and_creates_outputs(db_session):
    campaign, character = _setup(db_session)
    add_item(db_session, character.id, "Farinha", 5)
    add_item(db_session, character.id, "Água", 2)

    produced = produce_goods(
        db_session, campaign.id, character.id,
        inputs=[("Farinha", 3), ("Água", 1)],
        outputs=[("Pão", 4)],
    )

    assert len(produced) == 1 and produced[0].definition.name == "Pão" and produced[0].quantity == 4
    inventory = {i.definition.name: i.quantity for i in list_inventory(db_session, character.id)}
    assert inventory["Farinha"] == 2
    assert inventory["Água"] == 1
    assert inventory["Pão"] == 4


def test_production_without_enough_inputs_produces_nothing(db_session):
    campaign, character = _setup(db_session)
    add_item(db_session, character.id, "Farinha", 1)

    with pytest.raises(ProductionError):
        produce_goods(
            db_session, campaign.id, character.id,
            inputs=[("Farinha", 3)],
            outputs=[("Pão", 4)],
        )

    inventory = {i.definition.name: i.quantity for i in list_inventory(db_session, character.id)}
    assert inventory["Farinha"] == 1
    assert "Pão" not in inventory


def test_production_with_no_inputs_is_allowed(db_session):
    campaign, character = _setup(db_session)

    produced = produce_goods(
        db_session, campaign.id, character.id,
        inputs=[],
        outputs=[("Água Coletada", 3)],
    )

    assert produced[0].quantity == 3


def test_production_requires_at_least_one_output(db_session):
    campaign, character = _setup(db_session)

    with pytest.raises(ProductionError):
        produce_goods(db_session, campaign.id, character.id, inputs=[], outputs=[])


def test_production_checks_repeated_ingredient_totals_before_consuming_any(db_session):
    campaign, character = _setup(db_session)
    add_item(db_session, character.id, "Madeira", 4)

    with pytest.raises(ProductionError):
        produce_goods(
            db_session, campaign.id, character.id,
            inputs=[("Madeira", 2), ("Madeira", 3)],  # totals to 5, only 4 available
            outputs=[("Móvel", 1)],
        )

    inventory = {i.definition.name: i.quantity for i in list_inventory(db_session, character.id)}
    assert inventory["Madeira"] == 4
