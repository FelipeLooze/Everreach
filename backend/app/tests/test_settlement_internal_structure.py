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
from app.game.world.content_pools import (
    SERVICES_BY_SETTLEMENT_TYPE,
    STARTING_SETTLEMENT_REQUIRED_SERVICES,
)
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

        if location.id == _village.id:
            expected_types = set(SERVICES_BY_SETTLEMENT_TYPE["VILLAGE"])
            expected_types.update(STARTING_SETTLEMENT_REQUIRED_SERVICES)
            assert len(services) == len(expected_types)
        else:
            assert len(services) == expected_service_count


def test_starting_settlement_guarantees_basic_services_and_real_guilds(db_session):
    from app.core.enums import OrganizationType
    from app.db.models.organization import Organization
    from app.game.world.content_pools import SETTLEMENT_SERVICE_POOL

    campaign = create_campaign(db_session, "Campanha Inicial")
    _region, village = seed_initial_region(db_session, campaign.id)

    services = db_session.query(Location).filter(Location.parent_location_id == village.id).all()
    services_by_type = {service.type: service for service in services}
    required_types = {
        SETTLEMENT_SERVICE_POOL[key][1]
        for key in STARTING_SETTLEMENT_REQUIRED_SERVICES
    }
    assert required_types <= services_by_type.keys()

    guilds = (
        db_session.query(Organization)
        .filter(
            Organization.campaign_id == campaign.id,
            Organization.organization_type.in_([
                OrganizationType.GUILD.value,
                OrganizationType.COMMERCIAL.value,
            ]),
        )
        .all()
    )
    headquarters = {organization.headquarters_location_id for organization in guilds}
    assert services_by_type["adventurers_guild"].id in headquarters
    assert services_by_type["merchants_guild"].id in headquarters


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
