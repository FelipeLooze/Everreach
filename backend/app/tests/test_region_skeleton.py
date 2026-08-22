"""Phase 15C — Region Skeleton.

A massive Region is divided into many subregions before any deep local
materialization happens. The starting village always belongs to a fixed
anchor subregion ("Campos de Cardal") — everything else in the skeleton
is seed-driven and varies per campaign.
"""

from app.db.models.subregion import Subregion
from app.game.world.content_pools import ANCHOR_SUBREGION_NAME
from app.game.world.seed import create_campaign, seed_initial_region


def test_region_gets_many_subregions(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()

    assert 8 <= len(subregions) <= 14
    assert len({s.name for s in subregions}) == len(subregions)


def test_anchor_subregion_always_exists_first(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == region.id)
        .order_by(Subregion.order_index)
        .all()
    )

    assert subregions[0].name == ANCHOR_SUBREGION_NAME
    assert subregions[0].order_index == 0


def test_starting_village_belongs_to_the_anchor_subregion(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)

    anchor = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == region.id, Subregion.name == ANCHOR_SUBREGION_NAME)
        .one()
    )

    assert village.subregion_id == anchor.id


def test_skeleton_complete_flag_is_set_after_generation(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    assert region.skeleton_complete is True


def test_same_world_seed_reproduces_the_same_subregion_set(db_session):
    first_campaign = create_campaign(db_session, "Campanha 1", world_seed=99)
    second_campaign = create_campaign(db_session, "Campanha 2", world_seed=99)

    first_region, _ = seed_initial_region(db_session, first_campaign.id)
    second_region, _ = seed_initial_region(db_session, second_campaign.id)

    first_names = [
        s.name
        for s in db_session.query(Subregion)
        .filter(Subregion.region_id == first_region.id)
        .order_by(Subregion.order_index)
    ]
    second_names = [
        s.name
        for s in db_session.query(Subregion)
        .filter(Subregion.region_id == second_region.id)
        .order_by(Subregion.order_index)
    ]

    assert first_names == second_names
