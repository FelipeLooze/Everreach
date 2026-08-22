"""Phase 15A — Campaign World Seed & Generation Metadata.

world_seed is the one root of reproducibility for everything Phase 15
will generate: a Region's generation_seed is always *derived* from its
campaign's world_seed (never independently random), so the same campaign
always reproduces the same region-level seed. generation_version records
which generator logic produced a Region, kept separate from the seed
itself so a future generator rewrite can be detected without touching
already-persisted content.
"""

from app.game.world.generation import CURRENT_REGION_GENERATION_VERSION, derive_seed
from app.game.world.seed import create_campaign, seed_initial_region


def test_campaign_receives_a_world_seed_automatically(db_session):
    campaign = create_campaign(db_session, "Campanha A")

    assert campaign.world_seed is not None
    assert isinstance(campaign.world_seed, int)


def test_two_campaigns_receive_different_world_seeds(db_session):
    first = create_campaign(db_session, "Campanha A")
    second = create_campaign(db_session, "Campanha B")

    assert first.world_seed != second.world_seed


def test_explicit_world_seed_is_preserved(db_session):
    campaign = create_campaign(db_session, "Campanha Determinística", world_seed=872413923)

    assert campaign.world_seed == 872413923


def test_region_generation_seed_is_derived_from_campaign_world_seed(db_session):
    campaign = create_campaign(db_session, "Campanha Determinística", world_seed=872413923)
    region, _village = seed_initial_region(db_session, campaign.id)

    assert region.generation_seed == derive_seed(872413923, "region:0")


def test_same_campaign_world_seed_reproduces_the_same_region_seed(db_session):
    first_campaign = create_campaign(db_session, "Campanha 1", world_seed=555)
    second_campaign = create_campaign(db_session, "Campanha 2", world_seed=555)

    first_region, _ = seed_initial_region(db_session, first_campaign.id)
    second_region, _ = seed_initial_region(db_session, second_campaign.id)

    assert first_region.generation_seed == second_region.generation_seed


def test_region_records_its_generation_version(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    assert region.generation_version == CURRENT_REGION_GENERATION_VERSION == 1
