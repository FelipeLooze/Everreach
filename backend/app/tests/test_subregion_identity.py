"""Phase 15D — Subregions & Regional Identity.

Subregions are deliberately not interchangeable: each rolls its own
biome/danger/population/culture/economy. The anchor subregion (holding
the fixed starting village) stays constrained to a playable baseline.
"""

from app.core.enums import DangerLevel, SubregionBiome
from app.db.models.subregion import Subregion
from app.game.world.seed import create_campaign, seed_initial_region


def test_subregions_get_identity_fields(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()

    for subregion in subregions:
        assert subregion.biome in list(SubregionBiome)
        assert subregion.danger_level in list(DangerLevel)
        assert subregion.culture_summary != ""
        assert subregion.economy_summary != ""


def test_anchor_subregion_stays_playable(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    anchor = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == region.id, Subregion.order_index == 0)
        .one()
    )

    assert anchor.biome == SubregionBiome.PLAINS
    assert anchor.danger_level in (DangerLevel.SAFE, DangerLevel.LOW)


def test_subregions_are_not_all_identical(db_session):
    campaign = create_campaign(db_session, "Campanha com Variação", world_seed=7)
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()

    combos = {(s.biome, s.danger_level, s.population_density) for s in subregions}
    assert len(combos) > 1


def test_same_world_seed_reproduces_the_same_subregion_identities(db_session):
    first_campaign = create_campaign(db_session, "Campanha 1", world_seed=321)
    second_campaign = create_campaign(db_session, "Campanha 2", world_seed=321)

    first_region, _ = seed_initial_region(db_session, first_campaign.id)
    second_region, _ = seed_initial_region(db_session, second_campaign.id)

    first = [
        (s.name, s.biome, s.danger_level, s.population_density, s.culture_summary, s.economy_summary)
        for s in db_session.query(Subregion)
        .filter(Subregion.region_id == first_region.id)
        .order_by(Subregion.order_index)
    ]
    second = [
        (s.name, s.biome, s.danger_level, s.population_density, s.culture_summary, s.economy_summary)
        for s in db_session.query(Subregion)
        .filter(Subregion.region_id == second_region.id)
        .order_by(Subregion.order_index)
    ]

    assert first == second
