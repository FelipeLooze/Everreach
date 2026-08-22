"""Phase 16G — Alternative / Hidden Route Discovery."""

from app.core.enums import KnowerType
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.organization import Organization
from app.game.character.service import create_character
from app.game.world.boundaries import create_regional_boundary, get_boundary_routes
from app.game.world.route_discovery import discover_route_by_exploration
from app.game.world.seed import create_campaign, seed_initial_region


def _knows(db_session, campaign_id, knower_type, knower_id, fact_key) -> bool:
    fact = (
        db_session.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign_id, KnowledgeFact.fact_key == fact_key)
        .first()
    )
    if fact is None:
        return False
    return (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .first()
        is not None
    )


def test_local_leader_knows_publicly_known_routes_but_not_hidden_ones(db_session):
    found_hidden_case = False
    for seed in range(20):
        campaign = create_campaign(db_session, f"Lider Local {seed}", world_seed=seed)
        region, _village = seed_initial_region(db_session, campaign.id)
        boundary = create_regional_boundary(db_session, campaign.id, region.id)
        routes = get_boundary_routes(db_session, boundary.id)

        # Look the organization up the same way route_discovery does: by
        # the anchor settlement's own location, not the subregion id.
        from app.game.world.boundaries import _anchor_location_for_subregion

        anchor_location = _anchor_location_for_subregion(db_session, boundary.anchor_subregion_id)
        organization = (
            db_session.query(Organization)
            .filter(Organization.headquarters_location_id == anchor_location.id)
            .first()
        )
        assert organization is not None
        leader_id = organization.founder_id
        assert leader_id is not None

        for route in routes:
            known = _knows(db_session, campaign.id, KnowerType.NPC, leader_id, route.knowledge_fact_key)
            if route.is_publicly_known:
                assert known is True
            else:
                assert known is False
                found_hidden_case = True

    assert found_hidden_case


def test_exploration_grants_publicly_known_route_knowledge(db_session):
    campaign = create_campaign(db_session, "Exploracao", world_seed=9)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)
    boundary = create_regional_boundary(db_session, campaign.id, region.id)
    public_route = next(r for r in get_boundary_routes(db_session, boundary.id) if r.is_publicly_known)

    assert _knows(db_session, campaign.id, KnowerType.PLAYER, character.id, public_route.knowledge_fact_key) is False

    granted = discover_route_by_exploration(db_session, campaign.id, character.id, public_route)

    assert granted is True
    assert _knows(db_session, campaign.id, KnowerType.PLAYER, character.id, public_route.knowledge_fact_key) is True


def test_exploration_never_reveals_a_hidden_route(db_session):
    found_hidden_case = False
    for seed in range(20):
        campaign = create_campaign(db_session, f"Sem Revelar {seed}", world_seed=seed)
        region, village = seed_initial_region(db_session, campaign.id)
        character = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)
        boundary = create_regional_boundary(db_session, campaign.id, region.id)
        routes = get_boundary_routes(db_session, boundary.id)
        hidden = [r for r in routes if not r.is_publicly_known]
        if not hidden:
            continue
        found_hidden_case = True
        route = hidden[0]

        granted = discover_route_by_exploration(db_session, campaign.id, character.id, route)

        assert granted is False
        assert _knows(db_session, campaign.id, KnowerType.PLAYER, character.id, route.knowledge_fact_key) is False

    assert found_hidden_case
