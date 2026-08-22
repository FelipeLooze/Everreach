"""Phase 15F — Settlement Network.

Every non-anchor subregion gets one major (Tier 1) settlement plus a
handful of minor (Tier 2, stub) settlements. Exactly one settlement in
the region is upgraded to MAJOR_CITY. Names never collide.
"""

from app.core.enums import SettlementType
from app.db.models.location import Location
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.world.content_pools import ANCHOR_SUBREGION_NAME
from app.game.world.seed import create_campaign, seed_initial_region


def test_every_non_anchor_subregion_gets_one_major_settlement(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()
    non_anchor = [s for s in subregions if s.name != ANCHOR_SUBREGION_NAME]

    for subregion in non_anchor:
        major_locations = (
            db_session.query(Location)
            .join(Settlement, Settlement.location_id == Location.id)
            .filter(Location.subregion_id == subregion.id, Location.materialization_tier == 1)
            .all()
        )
        assert len(major_locations) == 1


def test_minor_settlements_are_tier_two_stubs(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    minor_locations = (
        db_session.query(Location)
        .filter(Location.region_id == region.id, Location.materialization_tier == 2)
        .all()
    )

    assert len(minor_locations) > 0
    for location in minor_locations:
        assert location.description == ""


def test_exactly_one_major_city_exists(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    major_cities = (
        db_session.query(Settlement)
        .join(Location, Location.id == Settlement.location_id)
        .filter(Location.region_id == region.id, Settlement.settlement_type == SettlementType.MAJOR_CITY)
        .all()
    )

    assert len(major_cities) == 1


def test_settlement_names_never_collide(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    names = [loc.name for loc in db_session.query(Location).filter(Location.region_id == region.id).all()]

    assert len(names) == len(set(names))


def test_settlements_carry_a_profile_and_population_tier(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    settlements = (
        db_session.query(Settlement)
        .join(Location, Location.id == Settlement.location_id)
        .filter(Location.region_id == region.id)
        .all()
    )

    for settlement in settlements:
        assert settlement.profile != ""
        assert settlement.population_tier >= 1


def test_same_world_seed_reproduces_the_same_settlement_network(db_session):
    first_campaign = create_campaign(db_session, "Campanha 1", world_seed=1234)
    second_campaign = create_campaign(db_session, "Campanha 2", world_seed=1234)

    first_region, _ = seed_initial_region(db_session, first_campaign.id)
    second_region, _ = seed_initial_region(db_session, second_campaign.id)

    first_names = sorted(
        loc.name for loc in db_session.query(Location).filter(Location.region_id == first_region.id)
    )
    second_names = sorted(
        loc.name for loc in db_session.query(Location).filter(Location.region_id == second_region.id)
    )

    assert first_names == second_names
