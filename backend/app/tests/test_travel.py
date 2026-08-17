import pytest
import random
from app.db.models.location import Location, LocationConnection
from app.game.discovery.service import discover_connection
from app.game.character.service import create_character
from app.game.travel.service import (
    TravelError, 
    move_character, 
    calculate_travel_minutes, 
    calculate_travel_stamina_cost,
    calculate_travel_incident_chance,
    roll_travel_incident,
)
from app.game.world.seed import create_campaign, seed_initial_region
from app.core.enums import MemoryOwnerType, TravelIncidentKind, TravelPace
from app.db.models.memory import Memory

def test_move_character_rejects_travel_without_enough_stamina(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Exhaustion",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        village.id,
    )

    forest = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.type == "forest",
        )
        .first()
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )

    discover_connection(
        db_session,
        character.id,
        connection.id,
    )

    character.stamina_current = 0.5

    try:
        move_character(
            db_session,
            campaign.id,
            character,
            forest.id,
        )
        assert False, "Expected TravelError"
    except TravelError as exc:
        assert "cansado demais" in str(exc)

    assert character.location_id == village.id
    assert character.stamina_current == 0.5

def test_move_character_spends_stamina(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Stamina Cost",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        village.id,
    )

    forest = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.type == "forest",
        )
        .first()
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )

    connection.danger = 0

    discover_connection(
        db_session,
        character.id,
        connection.id,
    )

    starting_stamina = character.stamina_current

    expected_cost = calculate_travel_stamina_cost(
        connection,
        TravelPace.NORMAL,
    )

    move_character(
        db_session,
        campaign.id,
        character,
        forest.id,
    )

    assert character.stamina_current == (
        starting_stamina - expected_cost
    )

def test_calculate_travel_stamina_cost_changes_with_pace(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Stamina",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
        )
        .first()
    )

    connection.distance = 2.0
    connection.travel_time_modifier = 1.5

    slow = calculate_travel_stamina_cost(
        connection,
        TravelPace.SLOW,
    )

    normal = calculate_travel_stamina_cost(
        connection,
        TravelPace.NORMAL,
    )

    fast = calculate_travel_stamina_cost(
        connection,
        TravelPace.FAST,
    )

    assert slow == 4.5
    assert normal == 6.0
    assert fast == 10.5

def test_move_character_follows_valid_connection(db_session):
    campaign = create_campaign(
        db_session,
        "Test Campaign",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        village.id,
    )

    db_session.commit()

    forest = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.type == "forest",
        )
        .first()
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )

    connection.danger = 0

    discover_connection(
        db_session,
        character.id,
        connection.id,
    )

    result = move_character(
        db_session,
        campaign.id,
        character,
        forest.id,
    )

    assert result.minutes > 0
    assert character.location_id == forest.id

def test_move_character_rejects_unconnected_location(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()

    clearing = db_session.query(Location).filter(Location.region_id == region.id, Location.name == "Clareira do Vidro Antigo").first()

    with pytest.raises(TravelError):
        move_character(db_session, campaign.id, character, clearing.id)

def test_calculate_travel_minutes_uses_distance_terrain_and_speed(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Calculation",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
        )
        .first()
    )

    connection.distance = 2.0
    connection.travel_time_modifier = 1.5

    normal_minutes = calculate_travel_minutes(
        connection,
    )

    faster_minutes = calculate_travel_minutes(
        connection,
        speed_multiplier=1.5,
    )

    slower_minutes = calculate_travel_minutes(
        connection,
        speed_multiplier=0.5,
    )

    assert normal_minutes == 45
    assert faster_minutes == 30
    assert slower_minutes == 90

def test_travel_incident_chance_increases_with_danger_and_duration(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Danger",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
        )
        .first()
    )

    connection.danger = 0

    safe = calculate_travel_incident_chance(
        connection,
        60,
    )

    connection.danger = 1

    low_danger = calculate_travel_incident_chance(
        connection,
        60,
    )

    connection.danger = 2

    higher_danger = calculate_travel_incident_chance(
        connection,
        60,
    )

    longer_exposure = calculate_travel_incident_chance(
        connection,
        120,
    )

    assert safe == 0.0

    assert (
        0.0
        < low_danger
        < higher_danger
        < longer_exposure
        < 1.0
    )

def test_roll_travel_incident_is_deterministic_with_rng(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Danger Roll",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
        )
        .first()
    )

    connection.danger = 5

    first = roll_travel_incident(
        connection,
        60,
        rng=random.Random(42),
    )

    second = roll_travel_incident(
        connection,
        60,
        rng=random.Random(42),
    )

    assert first == second

    assert 0.0 <= first.chance <= 1.0
    assert 0.0 <= first.roll < 1.0

    assert first.triggered == (
        first.roll < first.chance
    )

class SequenceRNG:
    def __init__(self, values):
        self.values = iter(values)

    def random(self):
        return next(self.values)

def test_move_character_delay_incident_adds_travel_time(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Delay Incident",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        village.id,
    )

    forest = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.type == "forest",
        )
        .first()
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )

    connection.danger = 5

    discover_connection(
        db_session,
        character.id,
        connection.id,
    )

    result = move_character(
        db_session,
        campaign.id,
        character,
        forest.id,
        rng=SequenceRNG([
            0.0,  # dispara o risco
            0.0,  # escolhe DELAY
        ]),
    )

    assert result.incident is not None
    assert result.incident.kind == TravelIncidentKind.DELAY
    assert result.incident.extra_minutes > 0

    assert result.minutes == (
        result.base_minutes
        + result.incident.extra_minutes
    )

    memory = (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == MemoryOwnerType.PLAYER.value,
            Memory.owner_id == character.id,
            Memory.summary_text.ilike("%viajou%"),
        )
        .order_by(Memory.created_at.desc())
        .first()
    )

    assert memory is not None
    assert forest.name in memory.summary_text
    assert "atraso" in memory.summary_text.lower()

def test_move_character_fatigue_incident_spends_extra_stamina(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Fatigue Incident",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        village.id,
    )

    forest = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.type == "forest",
        )
        .first()
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )

    connection.danger = 5

    discover_connection(
        db_session,
        character.id,
        connection.id,
    )

    starting_stamina = character.stamina_current

    normal_cost = calculate_travel_stamina_cost(
        connection,
        TravelPace.NORMAL,
    )

    result = move_character(
        db_session,
        campaign.id,
        character,
        forest.id,
        rng=SequenceRNG([
            0.0,  # dispara
            0.9,  # escolhe FATIGUE
        ]),
    )

    assert result.incident is not None
    assert result.incident.kind == TravelIncidentKind.FATIGUE

    assert result.incident.extra_stamina > 0

    assert result.stamina_spent == round(
        normal_cost + result.incident.extra_stamina,
        1,
    )

    assert character.stamina_current == max(
        0.0,
        starting_stamina - result.stamina_spent,
    )

    memory = (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == MemoryOwnerType.PLAYER.value,
            Memory.owner_id == character.id,
            Memory.summary_text.ilike("%viajou%"),
        )
        .order_by(Memory.created_at.desc())
        .first()
    )

    assert memory is not None
    assert forest.name in memory.summary_text
    assert "fadiga" in memory.summary_text.lower()