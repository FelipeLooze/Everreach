from types import SimpleNamespace

import pytest

from app.core.enums import (
    CombatActorType,
    CombatTacticalActionType,
    EncumbranceTier,
    ItemLocationType,
    TravelPace,
)
from app.db.models.location import Location, LocationConnection
from app.game.character.service import create_character
from app.game.combat.tactics import _agility_modifier, _encumbrance_adjusted_action_cost
from app.game.discovery.service import discover_connection
from app.game.inventory.service import add_item
from app.game.items.encumbrance import (
    EncumbranceRules,
    calculate_encumbrance,
    get_character_encumbrance,
)
from app.game.items.service import move_item_instance
from app.game.travel.service import calculate_travel_stamina_cost, move_character
from app.game.world.seed import create_campaign, seed_initial_region


def _world(db_session):
    campaign = create_campaign(db_session, "Encumbrance")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session, campaign.id, "Hero", region.id, location.id
    )
    return campaign, region, location, character


@pytest.mark.parametrize(
    ("weight", "expected"),
    [
        (12.5, EncumbranceTier.NORMAL),
        (12.6, EncumbranceTier.LIGHTLY_ENCUMBERED),
        (18.75, EncumbranceTier.LIGHTLY_ENCUMBERED),
        (18.8, EncumbranceTier.HEAVILY_ENCUMBERED),
        (25.0, EncumbranceTier.HEAVILY_ENCUMBERED),
        (25.1, EncumbranceTier.OVERLOADED),
    ],
)
def test_encumbrance_thresholds_are_explicit_and_testable(weight, expected):
    result = calculate_encumbrance(weight, strength=10)

    assert result.carrying_capacity == 25.0
    assert result.tier == expected


def test_encumbrance_rules_can_be_configured_without_changing_inventory_data():
    rules = EncumbranceRules(capacity_per_strength=4.0)

    result = calculate_encumbrance(30.0, strength=10, rules=rules)

    assert result.carrying_capacity == 40.0
    assert result.tier == EncumbranceTier.LIGHTLY_ENCUMBERED


def test_only_items_physically_carried_or_equipped_count_toward_load(db_session):
    _campaign, _region, location, character = _world(db_session)
    rations = add_item(
        db_session, character.id, "Rações", quantity=3, base_weight=1.5
    )
    armor = add_item(db_session, character.id, "Armadura", base_weight=8.0)
    dropped = add_item(db_session, character.id, "Pedra", base_weight=20.0)
    move_item_instance(
        db_session,
        armor,
        location_type=ItemLocationType.CHARACTER_EQUIPPED,
        location_ref=character.id,
    )
    move_item_instance(
        db_session,
        dropped,
        location_type=ItemLocationType.WORLD_LOCATION,
        location_ref=location.id,
    )

    result = get_character_encumbrance(db_session, character.id)

    assert rations.quantity == 3
    assert result.total_weight == 12.5
    assert result.tier == EncumbranceTier.NORMAL


def test_overloaded_character_keeps_items_and_pays_more_stamina_to_travel(db_session):
    campaign, region, village, character = _world(db_session)
    destination = (
        db_session.query(Location)
        .filter(Location.region_id == region.id, Location.id != village.id)
        .first()
    )
    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == destination.id,
        )
        .one()
    )
    connection.danger = 0
    discover_connection(db_session, character.id, connection.id)
    cargo = add_item(db_session, character.id, "Carga de minério", base_weight=30.0)
    normal_cost = calculate_travel_stamina_cost(connection, TravelPace.NORMAL)

    result = move_character(
        db_session,
        campaign.id,
        character,
        destination.id,
        pace=TravelPace.NORMAL,
    )

    assert cargo.location_ref == character.id
    assert result.stamina_spent == round(normal_cost * 1.75, 1)
    assert character.location_id == destination.id


def test_overload_increases_tactical_effort_and_penalizes_agility(db_session):
    _campaign, _region, _location, character = _world(db_session)
    add_item(db_session, character.id, "Carga pesada", base_weight=30.0)
    participant = SimpleNamespace(
        actor_type=CombatActorType.CHARACTER.value,
        actor_id=character.id,
    )

    dodge_cost = _encumbrance_adjusted_action_cost(
        db_session,
        participant,
        CombatTacticalActionType.DODGE,
    )

    assert dodge_cost == 3.5
    assert _agility_modifier(db_session, participant) == -4


def test_inventory_api_exposes_weight_capacity_and_encumbrance(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Weight API"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters",
        json={"name": "Hero"},
    ).json()
    add_item(
        db_session,
        character["id"],
        "Minério pesado",
        quantity=2,
        base_weight=15.0,
    )

    response = client.get(
        f"/api/campaigns/{campaign['id']}/inventory",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["unit_weight"] == 15.0
    assert payload["items"][0]["total_weight"] == 30.0
    assert payload["total_weight"] == 30.0
    assert payload["carrying_capacity"] == 25.0
    assert payload["encumbrance"] == "OVERLOADED"
