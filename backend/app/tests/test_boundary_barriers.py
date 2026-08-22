"""Phase 16C — Boundary Barriers."""

from collections import Counter

from app.core.enums import BoundaryBarrierCategory
from app.game.world.boundaries import create_regional_boundary, get_boundary_barriers
from app.game.world.seed import create_campaign, seed_initial_region


def test_every_boundary_gets_at_least_a_geographical_barrier(db_session):
    campaign = create_campaign(db_session, "Barreiras", world_seed=5)
    region, _village = seed_initial_region(db_session, campaign.id)

    boundary = create_regional_boundary(db_session, campaign.id, region.id)
    barriers = get_boundary_barriers(db_session, boundary.id)

    assert len(barriers) >= 1
    categories = [b.category for b in barriers]
    assert BoundaryBarrierCategory.GEOGRAPHICAL.value in categories
    assert categories.count(BoundaryBarrierCategory.GEOGRAPHICAL.value) == 1


def test_barriers_never_include_magical_by_default(db_session):
    # Roll many independent boundaries (one per synthetic campaign) to be
    # confident MAGICAL never appears, not just absent by luck once.
    all_categories: set[str] = set()
    for seed in range(30):
        campaign_n = create_campaign(db_session, f"Sem Magia {seed}", world_seed=seed)
        region_n, _village_n = seed_initial_region(db_session, campaign_n.id)
        boundary_n = create_regional_boundary(db_session, campaign_n.id, region_n.id)
        for barrier in get_boundary_barriers(db_session, boundary_n.id):
            all_categories.add(barrier.category)

    assert BoundaryBarrierCategory.MAGICAL.value not in all_categories


def test_barrier_categories_vary_across_seeds(db_session):
    barrier_counts = Counter()
    total_barrier_count = 0
    for seed in range(15):
        campaign_n = create_campaign(db_session, f"Variedade {seed}", world_seed=seed)
        region_n, _village_n = seed_initial_region(db_session, campaign_n.id)
        boundary_n = create_regional_boundary(db_session, campaign_n.id, region_n.id)
        barriers = get_boundary_barriers(db_session, boundary_n.id)
        total_barrier_count += len(barriers)
        for barrier in barriers:
            barrier_counts[barrier.category] += 1

    # At least one non-geographical category shows up somewhere across
    # 15 independent rolls, and boundary sizes aren't all identical.
    assert any(cat != BoundaryBarrierCategory.GEOGRAPHICAL.value for cat in barrier_counts)
    assert total_barrier_count > 15


def test_boundary_barriers_are_deterministic_per_seed(db_session):
    campaign_a = create_campaign(db_session, "Determinismo Barreira A", world_seed=123)
    region_a, _village_a = seed_initial_region(db_session, campaign_a.id)
    boundary_a = create_regional_boundary(db_session, campaign_a.id, region_a.id)
    barriers_a = get_boundary_barriers(db_session, boundary_a.id)

    campaign_b = create_campaign(db_session, "Determinismo Barreira B", world_seed=123)
    region_b, _village_b = seed_initial_region(db_session, campaign_b.id)
    boundary_b = create_regional_boundary(db_session, campaign_b.id, region_b.id)
    barriers_b = get_boundary_barriers(db_session, boundary_b.id)

    assert [(b.category, b.name) for b in barriers_a] == [(b.category, b.name) for b in barriers_b]
