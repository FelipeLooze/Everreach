"""Phase 15N — Deep Location Materialization.

Content-on-demand adds detail to an already-existing Tier 2 stub — it
never invents a place from nothing (the location, its subregion and its
connections already existed since Phase 15F/15H). Materializing is
idempotent and permanent: calling it twice never re-rolls content.
"""

from app.db.models.location import Location, LocationFeature
from app.db.models.settlement import Settlement
from app.game.world.materialization import ensure_location_materialized
from app.game.world.seed import create_campaign, seed_initial_region


def _a_minor_settlement(db_session, campaign_id):
    return db_session.query(Location).filter(Location.materialization_tier == 2).first()


def test_materializing_a_minor_settlement_fills_in_description_and_flips_tier(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    stub = _a_minor_settlement(db_session, campaign.id)
    assert stub is not None
    assert stub.description == ""

    materialized = ensure_location_materialized(db_session, stub)

    assert materialized.materialization_tier == 1
    assert materialized.description != ""


def test_materializing_a_minor_settlement_adds_a_feature_and_a_settlement_row(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    stub = _a_minor_settlement(db_session, campaign.id)
    ensure_location_materialized(db_session, stub)

    features = db_session.query(LocationFeature).filter(LocationFeature.location_id == stub.id).all()
    assert len(features) == 1

    settlement = db_session.query(Settlement).filter(Settlement.location_id == stub.id).one()
    assert settlement.profile != ""
    assert settlement.population_tier >= 1


def test_materializing_an_already_tier_one_location_is_a_no_op(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)

    original_description = village.description
    result = ensure_location_materialized(db_session, village)

    assert result.description == original_description
    assert result.materialization_tier == 1


def test_materializing_twice_never_duplicates_the_feature(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    stub = _a_minor_settlement(db_session, campaign.id)
    ensure_location_materialized(db_session, stub)
    ensure_location_materialized(db_session, stub)  # already Tier 1 now, must no-op

    features = db_session.query(LocationFeature).filter(LocationFeature.location_id == stub.id).all()
    assert len(features) == 1
