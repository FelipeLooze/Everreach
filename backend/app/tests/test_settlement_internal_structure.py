"""Phase 15G — Settlement Internal Structure.

Major settlements already know their internal services at generation
time (the backend already knows "this village has a blacksmith" — the
protagonist doesn't have to walk around until the LLM decides). Not
every settlement offers every service. MAJOR_CITY/CITY settlements get
an extra district layer; every other type attaches services directly.
"""

from app.core.enums import SettlementType
from app.db.models.location import Location
from app.db.models.settlement import Settlement
from app.game.world.content_pools import SERVICES_BY_SETTLEMENT_TYPE
from app.game.world.seed import create_campaign, seed_initial_region


def test_every_major_settlement_gets_its_defined_services(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    settlements = (
        db_session.query(Settlement)
        .join(Location, Location.id == Settlement.location_id)
        .filter(Location.region_id == region.id)
        .all()
    )

    for settlement in settlements:
        location = db_session.get(Location, settlement.location_id)
        expected_service_count = len(SERVICES_BY_SETTLEMENT_TYPE[str(settlement.settlement_type)])
        if expected_service_count == 0:
            continue

        if str(settlement.settlement_type) in ("MAJOR_CITY", "CITY"):
            central_district = (
                db_session.query(Location)
                .filter(Location.parent_location_id == location.id, Location.name.like("Distrito Central%"))
                .one()
            )
            services = (
                db_session.query(Location)
                .filter(Location.parent_location_id == central_district.id)
                .all()
            )
        else:
            services = (
                db_session.query(Location)
                .filter(Location.parent_location_id == location.id)
                .all()
            )

        assert len(services) == expected_service_count


def test_city_scale_settlements_get_seven_districts(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    city_settlements = (
        db_session.query(Settlement)
        .join(Location, Location.id == Settlement.location_id)
        .filter(
            Location.region_id == region.id,
            Settlement.settlement_type.in_([SettlementType.MAJOR_CITY, SettlementType.CITY]),
        )
        .all()
    )

    for settlement in city_settlements:
        districts = (
            db_session.query(Location)
            .filter(Location.parent_location_id == settlement.location_id, Location.type == "district")
            .all()
        )
        assert len(districts) == 7


def test_non_city_settlements_have_no_districts(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    non_city_settlements = (
        db_session.query(Settlement)
        .join(Location, Location.id == Settlement.location_id)
        .filter(
            Location.region_id == region.id,
            ~Settlement.settlement_type.in_([SettlementType.MAJOR_CITY, SettlementType.CITY]),
        )
        .all()
    )

    for settlement in non_city_settlements:
        districts = (
            db_session.query(Location)
            .filter(Location.parent_location_id == settlement.location_id, Location.type == "district")
            .all()
        )
        assert districts == []


def test_isolated_settlements_have_no_services(db_session):
    """ISOLATED_SETTLEMENT deliberately has an empty service list — not
    every settlement contains identical services (spec)."""
    assert SERVICES_BY_SETTLEMENT_TYPE["ISOLATED_SETTLEMENT"] == []
