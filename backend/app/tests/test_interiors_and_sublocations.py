"""Phase 15O — Interiors & Sublocations.

Fixes a real Phase 15G gap found while auditing this subphase: districts
and services had a parent_location_id but no LocationConnection, making
them permanently unreachable under the existing travel system. Interiors
materialize on demand (Tier 3), as a child of an already-existing,
already-Tier-1 service location — never generated in bulk up front.
"""

from app.db.models.location import Location, LocationConnection
from app.game.world.materialization import ensure_location_materialized
from app.game.world.seed import create_campaign, seed_initial_region


def test_every_district_and_service_has_a_connection_to_its_parent(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    internal_locations = (
        db_session.query(Location)
        .filter(Location.region_id == region.id, Location.parent_location_id.isnot(None))
        .all()
    )
    assert len(internal_locations) > 0

    for location in internal_locations:
        connection = (
            db_session.query(LocationConnection)
            .filter(
                LocationConnection.from_location_id == location.parent_location_id,
                LocationConnection.to_location_id == location.id,
            )
            .first()
        )
        assert connection is not None


def test_materializing_an_interior_eligible_service_creates_a_tier_three_child(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    blacksmith = (
        db_session.query(Location)
        .filter(Location.region_id == region.id, Location.type == "blacksmith")
        .first()
    )
    assert blacksmith is not None

    ensure_location_materialized(db_session, blacksmith)

    interior = (
        db_session.query(Location)
        .filter(Location.parent_location_id == blacksmith.id, Location.materialization_tier == 3)
        .one()
    )
    assert interior.description != ""
    assert interior.type == "interior"

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == blacksmith.id,
            LocationConnection.to_location_id == interior.id,
        )
        .first()
    )
    assert connection is not None


def test_materializing_an_interior_twice_never_duplicates_it(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    blacksmith = (
        db_session.query(Location)
        .filter(Location.region_id == region.id, Location.type == "blacksmith")
        .first()
    )

    ensure_location_materialized(db_session, blacksmith)
    ensure_location_materialized(db_session, blacksmith)

    interiors = (
        db_session.query(Location)
        .filter(Location.parent_location_id == blacksmith.id, Location.materialization_tier == 3)
        .all()
    )
    assert len(interiors) == 1


def test_market_square_has_no_interior_concept(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    market_square = (
        db_session.query(Location)
        .filter(Location.region_id == region.id, Location.type == "market_square")
        .first()
    )
    if market_square is None:
        return  # not every generated region necessarily has a MAJOR_CITY/CITY settlement seed roll

    ensure_location_materialized(db_session, market_square)

    interiors = (
        db_session.query(Location)
        .filter(Location.parent_location_id == market_square.id)
        .all()
    )
    assert interiors == []
