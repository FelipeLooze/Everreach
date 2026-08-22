"""Phase 15B — Initial Massive Region Generation: macro identity.

The Region's climate/culture/history summaries come from the generation
pipeline (app.game.world.generator), deterministic per generation_seed —
same campaign world_seed always reproduces the same identity text.
"""

from app.game.world.content_pools import (
    CLIMATE_SUMMARIES,
    CULTURAL_SUMMARIES,
    HISTORICAL_SUMMARIES,
)
from app.game.world.seed import create_campaign, seed_initial_region


def test_region_receives_generated_identity_summaries(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    assert region.climate_summary in CLIMATE_SUMMARIES
    assert region.cultural_summary in CULTURAL_SUMMARIES
    assert region.historical_summary in HISTORICAL_SUMMARIES


def test_same_world_seed_reproduces_the_same_region_identity(db_session):
    first_campaign = create_campaign(db_session, "Campanha 1", world_seed=42)
    second_campaign = create_campaign(db_session, "Campanha 2", world_seed=42)

    first_region, _ = seed_initial_region(db_session, first_campaign.id)
    second_region, _ = seed_initial_region(db_session, second_campaign.id)

    assert first_region.climate_summary == second_region.climate_summary
    assert first_region.cultural_summary == second_region.cultural_summary
    assert first_region.historical_summary == second_region.historical_summary


def test_different_world_seeds_can_reproduce_different_region_identity(db_session):
    seeds_seen = set()
    for seed in range(8):
        campaign = create_campaign(db_session, f"Campanha {seed}", world_seed=seed)
        region, _ = seed_initial_region(db_session, campaign.id)
        seeds_seen.add((region.climate_summary, region.cultural_summary, region.historical_summary))

    assert len(seeds_seen) > 1


def test_region_name_stays_pinned_to_the_canonical_starting_region(db_session):
    """Phase 15's massive procedural world builds OUTWARD from a fixed,
    named anchor region/settlement (Vale Verdejante / Cardal) rather than
    randomizing the player's own starting point — only what surrounds it
    is procedurally generated (subregions, settlements, geography...)."""
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)

    assert region.name == "Vale Verdejante"
    assert village.name == "Cardal"
