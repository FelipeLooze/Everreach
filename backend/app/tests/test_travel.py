import pytest
from app.db.models.location import Location, LocationConnection
from app.game.discovery.service import discover_connection
from app.game.character.service import create_character
from app.game.travel.service import TravelError, move_character, calculate_travel_minutes, calculate_travel_stamina_cost
from app.game.world.seed import create_campaign, seed_initial_region
from app.core.enums import TravelPace

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

    discover_connection(
        db_session,
        character.id,
        connection.id,
    )

    minutes = move_character(
        db_session,
        campaign.id,
        character,
        forest.id,
    )

    assert minutes > 0
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
