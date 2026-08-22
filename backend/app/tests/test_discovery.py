from app.core.enums import DiscoveryStatus, ActionIntentType, EventType
from app.game.character.service import create_character
from app.game.discovery.service import (
    get_connection_discovery,
    get_location_discovery,
    set_location_discovery,
)
from app.game.world.seed import create_campaign, seed_initial_region
from app.game.map.service import known_map
from app.db.models.event import WorldEvent
from app.ai.intent_parser import Intent
from app.db.models.location import (
    CharacterLocationDiscovery,
    CharacterConnectionDiscovery,
    Location,
    LocationConnection,
)
from app.game import engine
from app.game.game_state import build_game_state
from app.game.perception.service import observe_surroundings


def test_location_discovery_is_individual_per_character(db_session):
    campaign = create_campaign(db_session, "Discovery Test")
    region, village = seed_initial_region(db_session, campaign.id)

    first = create_character(
        db_session,
        campaign.id,
        "First",
        region.id,
        village.id,
    )

    second = create_character(
        db_session,
        campaign.id,
        "Second",
        region.id,
        village.id,
    )

    set_location_discovery(
        db_session,
        first.id,
        village.id,
        DiscoveryStatus.VISITED,
    )

    first_discovery = get_location_discovery(
        db_session,
        first.id,
        village.id,
    )

    second_discovery = get_location_discovery(
        db_session,
        second.id,
        village.id,
    )

    assert first_discovery is not None
    assert first_discovery.status == DiscoveryStatus.VISITED
    assert second_discovery is None


def test_location_discovery_only_moves_forward(db_session):
    campaign = create_campaign(db_session, "Discovery Progression")
    region, village = seed_initial_region(db_session, campaign.id)

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        village.id,
    )

    discovery, changed = set_location_discovery(
        db_session,
        character.id,
        village.id,
        DiscoveryStatus.RUMORED,
    )

    assert changed is True
    assert discovery.status == DiscoveryStatus.RUMORED
    assert discovery.discovered_at is None
    assert discovery.visited_at is None

    discovery, changed = set_location_discovery(
        db_session,
        character.id,
        village.id,
        DiscoveryStatus.VISITED,
    )

    assert changed is True
    assert discovery.status == DiscoveryStatus.VISITED
    assert discovery.discovered_at is not None
    assert discovery.visited_at is not None

    discovery, changed = set_location_discovery(
        db_session,
        character.id,
        village.id,
        DiscoveryStatus.DISCOVERED,
    )

    assert changed is False
    assert discovery.status == DiscoveryStatus.VISITED

    discovery, changed = set_location_discovery(
        db_session,
        character.id,
        village.id,
        DiscoveryStatus.MAPPED,
    )

    assert changed is True
    assert discovery.status == DiscoveryStatus.MAPPED
    assert discovery.mapped_at is not None


def test_world_start_marks_initial_location_as_visited(
    client,
    db_session,
):
    campaign = client.post(
        "/api/campaigns",
        json={"name": "Arrival Discovery"},
    ).json()

    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters",
        json={"name": "Hero"},
    ).json()

    response = client.post(
        f"/api/campaigns/{campaign['id']}/start",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200

    location_id = response.json()["state"]["location"]["id"]

    discovery = (
        db_session.query(CharacterLocationDiscovery)
        .filter(
            CharacterLocationDiscovery.character_id == character["id"],
            CharacterLocationDiscovery.location_id == location_id,
        )
        .one()
    )

    assert discovery.status == DiscoveryStatus.VISITED
    assert discovery.discovered_at is not None
    assert discovery.visited_at is not None

def test_known_map_is_individual_per_character(db_session):
    campaign = create_campaign(
        db_session,
        "Individual Map",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    forest = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.type == "forest",
        )
        .first()
    )

    first = create_character(
        db_session,
        campaign.id,
        "First",
        region.id,
        village.id,
    )

    second = create_character(
        db_session,
        campaign.id,
        "Second",
        region.id,
        village.id,
    )

    set_location_discovery(
        db_session,
        first.id,
        village.id,
        DiscoveryStatus.VISITED,
    )

    set_location_discovery(
        db_session,
        second.id,
        village.id,
        DiscoveryStatus.VISITED,
    )

    set_location_discovery(
        db_session,
        first.id,
        forest.id,
        DiscoveryStatus.DISCOVERED,
    )

    first_map = known_map(
        db_session,
        campaign.id,
        first.id,
    )

    second_map = known_map(
        db_session,
        campaign.id,
        second.id,
    )

    first_names = {
        location.name
        for location in first_map["locations"]
    }

    second_names = {
        location.name
        for location in second_map["locations"]
    }

    assert village.name in first_names
    assert village.name in second_names

    assert forest.name in first_names
    assert forest.name not in second_names

def test_observe_discovers_route_only_for_observing_character(db_session):
    campaign = create_campaign(
        db_session,
        "Perception Isolation",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
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
        .first()
    )

    first = create_character(
        db_session,
        campaign.id,
        "First",
        region.id,
        village.id,
    )

    second = create_character(
        db_session,
        campaign.id,
        "Second",
        region.id,
        village.id,
    )

    observe_surroundings(
        db_session,
        first,
    )

    first_connection = get_connection_discovery(
        db_session,
        first.id,
        connection.id,
    )

    second_connection = get_connection_discovery(
        db_session,
        second.id,
        connection.id,
    )

    assert first_connection is not None
    assert second_connection is None

    first_location = get_location_discovery(
        db_session,
        first.id,
        forest.id,
    )

    second_location = get_location_discovery(
        db_session,
        second.id,
        forest.id,
    )

    assert first_location is not None
    assert first_location.status == DiscoveryStatus.DISCOVERED

    assert second_location is None

def test_known_map_shows_only_character_discovered_connections(db_session):
    campaign = create_campaign(
        db_session,
        "Connection Map Isolation",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    first = create_character(
        db_session,
        campaign.id,
        "First",
        region.id,
        village.id,
    )

    second = create_character(
        db_session,
        campaign.id,
        "Second",
        region.id,
        village.id,
    )

    set_location_discovery(
        db_session,
        first.id,
        village.id,
        DiscoveryStatus.VISITED,
    )

    set_location_discovery(
        db_session,
        second.id,
        village.id,
        DiscoveryStatus.VISITED,
    )

    observe_surroundings(
        db_session,
        first,
    )

    first_map = known_map(
        db_session,
        campaign.id,
        first.id,
    )

    second_map = known_map(
        db_session,
        campaign.id,
        second.id,
    )

    assert len(first_map["connections"]) > 0
    assert second_map["connections"] == []

def test_observe_makes_discovered_destination_available_for_travel(db_session):
    campaign = create_campaign(
        db_session,
        "Observe Then Travel",
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

    observe_surroundings(
        db_session,
        character,
    )

    discovery = get_location_discovery(
        db_session,
        character.id,
        forest.id,
    )

    assert discovery is not None
    assert discovery.status == DiscoveryStatus.DISCOVERED

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    intent = Intent(
        type=ActionIntentType.MOVE,
        target=forest.name,
        raw_text="Vou até o bosque.",
    )

    summary, minutes = engine._apply_intent(
        db_session,
        campaign.id,
        character,
        intent,
        state,
    )

    assert minutes > 0
    assert character.location_id == forest.id

    discovery = get_location_discovery(
        db_session,
        character.id,
        forest.id,
    )

    assert discovery is not None
    assert discovery.status == DiscoveryStatus.VISITED

def test_observe_logs_discovery_events_only_once(db_session):
    campaign = create_campaign(
        db_session,
        "Discovery Events",
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

    observe_surroundings(
        db_session,
        character,
    )

    first_location_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.actor_id == character.id,
            WorldEvent.event_type
            == EventType.LOCATION_DISCOVERED.value,
        )
        .count()
    )

    first_connection_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.actor_id == character.id,
            WorldEvent.event_type
            == EventType.CONNECTION_DISCOVERED.value,
        )
        .count()
    )

    assert first_location_events > 0
    assert first_connection_events > 0

    observe_surroundings(
        db_session,
        character,
    )

    assert (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.actor_id == character.id,
            WorldEvent.event_type
            == EventType.LOCATION_DISCOVERED.value,
        )
        .count()
        == first_location_events
    )

    assert (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.actor_id == character.id,
            WorldEvent.event_type
            == EventType.CONNECTION_DISCOVERED.value,
        )
        .count()
        == first_connection_events
    )

def test_known_destination_without_known_route_cannot_be_traveled(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Unknown Route",
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

    set_location_discovery(
        db_session,
        character.id,
        forest.id,
        DiscoveryStatus.DISCOVERED,
    )

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    intent = Intent(
        type=ActionIntentType.MOVE,
        target=forest.name,
        raw_text="Vou até o bosque.",
    )

    summary, minutes = engine._apply_intent(
        db_session,
        campaign.id,
        character,
        intent,
        state,
    )

    assert minutes == 0
    assert character.location_id == village.id
    assert "não conhece uma rota" in summary.lower()