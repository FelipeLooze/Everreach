"""Phase 17D — Exploration & Discovery."""

from app.core.enums import ConnectionType, EventType, GeographicKnowledgeAspect, KnowerType
from app.db.models.event import WorldEvent
from app.db.models.location import CharacterConnectionDiscovery, Location, LocationConnection
from app.game.character.service import create_character
from app.game.discovery.service import discover_connection, get_location_discovery
from app.game.exploration.service import EXPLORATION_MINUTES, explore_current_location
from app.game.knowledge.geography import knows_geographic_aspect
from app.game.time.clock import get_world_time
from app.game.world.seed import create_campaign, seed_initial_region


class _FixedRoll:
    """A tiny fake rng: forces d20's raw roll and picks the first
    candidate for weighted choice, so success/failure is deterministic."""

    def __init__(self, raw: int):
        self.raw = raw

    def randint(self, a, b):
        return self.raw

    def choices(self, population, weights=None, k=1):
        return [population[0]] * k


def _setup(db_session, world_seed):
    campaign = create_campaign(db_session, f"Exploracao {world_seed}", world_seed=world_seed)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)
    return campaign, region, village, character


def test_nothing_to_find_returns_unsuccessful_but_still_spends_time(db_session):
    campaign, region, village, character = _setup(db_session, 1)

    # Mark every outgoing connection from the village as already known,
    # so nothing is left to discover.
    connections = db_session.query(LocationConnection).filter(LocationConnection.from_location_id == village.id).all()
    for connection in connections:
        discover_connection(db_session, character.id, connection.id)

    before_minute = get_world_time(db_session, campaign.id).total_minutes()
    outcome = explore_current_location(db_session, campaign.id, character)
    after_minute = get_world_time(db_session, campaign.id).total_minutes()

    assert outcome.success is False
    assert outcome.found_connection_id is None
    assert after_minute - before_minute == EXPLORATION_MINUTES

    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.campaign_id == campaign.id, WorldEvent.event_type == EventType.EXPLORATION_ATTEMPTED.value)
        .one()
    )
    assert event.payload_json is not None


def test_successful_search_discovers_a_connection_and_grants_knowledge(db_session):
    campaign, region, village, character = _setup(db_session, 2)

    outcome = explore_current_location(db_session, campaign.id, character, rng=_FixedRoll(20))

    assert outcome.success is True
    assert outcome.found_connection_id is not None
    assert outcome.found_location_id is not None

    discovery = get_location_discovery(db_session, character.id, outcome.found_location_id)
    assert discovery is not None
    assert discovery.status == "DISCOVERED"

    connection_known = (
        db_session.query(CharacterConnectionDiscovery)
        .filter(
            CharacterConnectionDiscovery.character_id == character.id,
            CharacterConnectionDiscovery.connection_id == outcome.found_connection_id,
        )
        .first()
    )
    assert connection_known is not None

    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        "location", outcome.found_location_id, GeographicKnowledgeAspect.EXISTENCE,
    ) is True


def test_failed_search_finds_nothing(db_session):
    campaign, region, village, character = _setup(db_session, 3)

    outcome = explore_current_location(db_session, campaign.id, character, rng=_FixedRoll(1))

    assert outcome.success is False
    assert outcome.found_connection_id is None


def test_already_known_connections_are_never_rediscovered(db_session):
    campaign, region, village, character = _setup(db_session, 4)

    connections = db_session.query(LocationConnection).filter(LocationConnection.from_location_id == village.id).all()
    assert len(connections) >= 1
    already_known = connections[0]
    discover_connection(db_session, character.id, already_known.id)

    outcome = explore_current_location(db_session, campaign.id, character, rng=_FixedRoll(20))

    if outcome.success:
        assert outcome.found_connection_id != already_known.id


def test_discovery_events_are_logged_for_a_successful_search(db_session):
    campaign, region, village, character = _setup(db_session, 5)

    explore_current_location(db_session, campaign.id, character, rng=_FixedRoll(20))

    event_types = {
        row[0]
        for row in db_session.query(WorldEvent.event_type).filter(WorldEvent.campaign_id == campaign.id).all()
    }
    assert EventType.CONNECTION_DISCOVERED.value in event_types
    assert EventType.LOCATION_DISCOVERED.value in event_types
    assert EventType.EXPLORATION_ATTEMPTED.value in event_types
