"""Phase 15I — Major Points of Interest.

Every non-anchor subregion gets 1-2 major POIs (ruins, caves, mines...),
persistent regardless of player discovery, and reachable (remotely,
dangerously) from its subregion's major settlement.
"""

from app.db.models.location import Location, LocationConnection
from app.db.models.subregion import Subregion
from app.game.world.content_pools import POI_POOL
from app.game.world.seed import create_campaign, seed_initial_region

POI_TYPES = {poi_type for _name, poi_type, _desc in POI_POOL}


def test_every_non_anchor_subregion_gets_at_least_one_poi(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()
    non_anchor = [s for s in subregions if s.order_index != 0]

    for subregion in non_anchor:
        pois = (
            db_session.query(Location)
            .filter(Location.subregion_id == subregion.id, Location.type.in_(POI_TYPES))
            .all()
        )
        assert 1 <= len(pois) <= 2


def test_pois_are_connected_to_their_subregions_major_settlement(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    pois = db_session.query(Location).filter(Location.region_id == region.id, Location.type.in_(POI_TYPES)).all()
    assert len(pois) > 0

    for poi in pois:
        connections = (
            db_session.query(LocationConnection)
            .filter(LocationConnection.to_location_id == poi.id)
            .all()
        )
        assert len(connections) >= 1
        assert connections[0].connection_type == "TRAIL"


def test_poi_names_never_collide_with_other_generated_content(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    names = [loc.name for loc in db_session.query(Location).filter(Location.region_id == region.id).all()]

    assert len(names) == len(set(names))
