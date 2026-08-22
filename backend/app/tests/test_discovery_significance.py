"""Phase 17L — Discovery Events."""

import json

from app.core.enums import DiscoverySignificance, EventType
from app.db.models.event import WorldEvent
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.discovery.service import discover_connection
from app.game.exploration.discovery_significance import assess_location_discovery_significance
from app.game.exploration.service import explore_current_location
from app.game.world.seed import create_campaign, seed_initial_region


def test_a_settlement_is_a_major_discovery():
    village = Location(region_id="r", name="Vila", type="village", materialization_tier=1)
    assert assess_location_discovery_significance(village) == DiscoverySignificance.MAJOR


def test_a_region_frontier_is_a_major_discovery():
    frontier = Location(region_id="r", name="Fronteira", type="region_frontier", materialization_tier=1)
    assert assess_location_discovery_significance(frontier) == DiscoverySignificance.MAJOR


def test_a_poi_is_a_notable_discovery():
    poi = Location(region_id="r", name="Ruína Antiga", type="ruins", materialization_tier=1)
    assert assess_location_discovery_significance(poi) == DiscoverySignificance.NOTABLE


def test_an_interior_is_only_a_minor_discovery():
    interior = Location(region_id="r", name="Interior da Taverna", type="interior", materialization_tier=3)
    assert assess_location_discovery_significance(interior) == DiscoverySignificance.MINOR


def test_exploration_outcome_carries_significance_end_to_end(db_session):
    class _FixedRoll:
        def randint(self, a, b):
            return 20

        def choices(self, population, weights=None, k=1):
            return [population[0]] * k

    campaign = create_campaign(db_session, "Significancia Fim A Fim", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)

    outcome = explore_current_location(db_session, campaign.id, character, rng=_FixedRoll())

    assert outcome.success is True
    assert outcome.significance is not None

    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.campaign_id == campaign.id, WorldEvent.event_type == EventType.LOCATION_DISCOVERED.value)
        .one()
    )
    payload = json.loads(event.payload_json)
    assert payload["significance"] == outcome.significance.value
