"""Phase 16F — Crossing Feasibility & Hazard Evaluation."""

from app.core.enums import CombatActorType, CrossingFeasibilityVerdict, EconomicActorType, GroupType, KnowerType
from app.game.character.service import create_character
from app.game.economy.actors import deposit_to_actor
from app.game.groups.service import create_group
from app.game.inventory.service import add_item
from app.game.npcs.service import teach_fact
from app.game.time.clock import advance_world_time
from app.game.world.boundaries import create_regional_boundary, get_boundary_routes, route_accessibility_for_season
from app.game.world.crossing import evaluate_crossing_feasibility
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session, world_seed):
    campaign = create_campaign(db_session, f"Travessia {world_seed}", world_seed=world_seed)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)
    boundary = create_regional_boundary(db_session, campaign.id, region.id)
    route = get_boundary_routes(db_session, boundary.id)[0]
    return campaign, region, character, route


def test_unprepared_character_gets_a_cautionary_verdict(db_session):
    campaign, _region, character, route = _setup(db_session, world_seed=1)

    assessment = evaluate_crossing_feasibility(db_session, campaign.id, character.id, route)

    assert assessment.verdict in {
        CrossingFeasibilityVerdict.POSSIBLE_BUT_DANGEROUS.value,
        CrossingFeasibilityVerdict.LIKELY_TO_FAIL.value,
    }
    assert assessment.money_bronze == 0
    assert assessment.companion_count == 0
    assert assessment.knows_route is False
    assert len(assessment.concerns) > 0


def test_well_prepared_character_scores_better_than_unprepared(db_session):
    campaign, region, character, route = _setup(db_session, world_seed=2)

    unprepared = evaluate_crossing_feasibility(db_session, campaign.id, character.id, route)

    deposit_to_actor(
        db_session, EconomicActorType.CHARACTER, character.id, campaign.id,
        int(route.estimated_distance * 10), reason="preparação para expedição",
    )
    for i in range(6):
        add_item(db_session, character.id, f"Suprimento {i}", quantity=1)

    companion = create_character(db_session, campaign.id, "Companheira", region_id=region.id)
    create_group(
        db_session, campaign.id,
        group_type=GroupType.OTHER,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.CHARACTER, companion.id),
        ],
    )

    teach_fact(db_session, campaign.id, route.knowledge_fact_key, KnowerType.PLAYER, character.id)

    prepared = evaluate_crossing_feasibility(db_session, campaign.id, character.id, route)

    assert prepared.money_bronze > unprepared.money_bronze
    assert prepared.companion_count == 1
    assert prepared.knows_route is True
    assert len(prepared.concerns) < len(unprepared.concerns)

    verdict_rank = {
        CrossingFeasibilityVerdict.LIKELY_TO_FAIL.value: 0,
        CrossingFeasibilityVerdict.POSSIBLE_BUT_DANGEROUS.value: 1,
        CrossingFeasibilityVerdict.FEASIBLE.value: 2,
    }
    assert verdict_rank[prepared.verdict] >= verdict_rank[unprepared.verdict]


def test_estimated_cost_scales_with_route_distance(db_session):
    campaign, _region, character, route = _setup(db_session, world_seed=3)

    assessment = evaluate_crossing_feasibility(db_session, campaign.id, character.id, route)

    from app.game.world.crossing import BRONZE_COST_PER_DISTANCE_UNIT

    assert assessment.estimated_cost_bronze == int(route.estimated_distance * BRONZE_COST_PER_DISTANCE_UNIT)


def test_verdict_never_depends_on_character_level(db_session):
    campaign, region, low, route = _setup(db_session, world_seed=4)
    high = create_character(db_session, campaign.id, "Veterana", region_id=region.id, location_id=None)
    high.level = 40
    db_session.flush()

    low_assessment = evaluate_crossing_feasibility(db_session, campaign.id, low.id, route)
    high_assessment = evaluate_crossing_feasibility(db_session, campaign.id, high.id, route)

    # Identical (zero) preparation on both — level alone must not move
    # the verdict.
    assert low_assessment.verdict == high_assessment.verdict


def test_assessment_never_repeats_route_or_barrier_description_text(db_session):
    from app.game.world.boundaries import get_boundary_barriers

    campaign, region, character, route = _setup(db_session, world_seed=5)
    boundary_id = route.boundary_id
    barriers = get_boundary_barriers(db_session, boundary_id)

    assessment = evaluate_crossing_feasibility(db_session, campaign.id, character.id, route)
    concerns_text = " ".join(assessment.concerns)

    assert route.description not in concerns_text
    for barrier in barriers:
        assert barrier.description not in concerns_text


def test_accessibility_field_matches_current_season(db_session):
    campaign, _region, character, route = _setup(db_session, world_seed=6)

    assessment = evaluate_crossing_feasibility(db_session, campaign.id, character.id, route)

    from app.game.time.clock import current_season

    season = current_season(db_session, campaign.id)
    assert assessment.accessibility == route_accessibility_for_season(route, season.value)
