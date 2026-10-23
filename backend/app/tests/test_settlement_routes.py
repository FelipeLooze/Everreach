"""From one building to another of the same settlement, through the square."""
from app.core.enums import EventType
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.db.models.location import Location
from app.game.discovery.service import discover_connection, set_location_discovery
from app.game.travel import settlement_routes
from app.game.travel.service import find_connection


def test_walking_from_one_building_to_another_crosses_the_square(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Settlement routes"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(f"/api/campaigns/{campaign['id']}/start", params={"character_id": character_data["id"]})
    character = db_session.get(Character, character_data["id"])
    square_id = character.location_id
    first, second = (
        db_session.query(Location)
        .filter(Location.parent_location_id == square_id)
        .order_by(Location.id)
        .limit(2)
        .all()
    )
    assert find_connection(db_session, first.id, second.id) is None
    # Learned the way a player would at the square: both buildings and the
    # paths to them. The way back from a building is learned by being there.
    for building in (first, second):
        set_location_discovery(db_session, character.id, building.id, "DISCOVERED")
        discover_connection(db_session, character.id, find_connection(db_session, square_id, building.id).id)

    settlement_routes.move_within_reach(db_session, campaign["id"], character, first.id)
    result = settlement_routes.move_within_reach(db_session, campaign["id"], character, second.id)

    assert character.location_id == second.id
    moves = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.campaign_id == campaign["id"], WorldEvent.event_type == EventType.PLAYER_MOVED)
        .count()
    )
    assert moves == 3  # square -> first, first -> square, square -> second
    assert result.minutes > 0


def test_an_unknown_second_leg_does_not_strand_the_character_at_the_square(client, db_session):
    import pytest

    from app.game.travel.service import TravelError

    campaign = client.post("/api/campaigns", json={"name": "Settlement routes 2"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(f"/api/campaigns/{campaign['id']}/start", params={"character_id": character_data["id"]})
    character = db_session.get(Character, character_data["id"])
    square_id = character.location_id
    first, second = (
        db_session.query(Location).filter(Location.parent_location_id == square_id)
        .order_by(Location.id).limit(2).all()
    )
    set_location_discovery(db_session, character.id, first.id, "DISCOVERED")
    discover_connection(db_session, character.id, find_connection(db_session, square_id, first.id).id)
    set_location_discovery(db_session, character.id, second.id, "DISCOVERED")
    settlement_routes.move_within_reach(db_session, campaign["id"], character, first.id)

    with pytest.raises(TravelError):
        settlement_routes.move_within_reach(db_session, campaign["id"], character, second.id)
    assert character.location_id == first.id
