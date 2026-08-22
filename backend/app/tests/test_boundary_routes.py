"""Phase 16D — Cross-Region Routes."""

from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.game.world.boundaries import create_regional_boundary, get_boundary_routes
from app.game.world.seed import create_campaign, seed_initial_region


def test_a_boundary_always_has_at_least_two_routes_with_different_tradeoffs(db_session):
    campaign = create_campaign(db_session, "Rotas", world_seed=3)
    region, _village = seed_initial_region(db_session, campaign.id)

    boundary = create_regional_boundary(db_session, campaign.id, region.id)
    routes = get_boundary_routes(db_session, boundary.id)

    assert len(routes) >= 2
    assert len(routes) <= 3

    distances = {r.estimated_distance for r in routes}
    dangers = {r.danger_hint for r in routes}
    assert len(distances) > 1 or len(dangers) > 1

    names = [r.name for r in routes]
    assert len(names) == len(set(names))


def test_every_route_originates_at_the_boundary_frontier_and_has_no_destination_yet(db_session):
    campaign = create_campaign(db_session, "Origem Das Rotas", world_seed=8)
    region, _village = seed_initial_region(db_session, campaign.id)

    boundary = create_regional_boundary(db_session, campaign.id, region.id)
    routes = get_boundary_routes(db_session, boundary.id)

    for route in routes:
        assert route.origin_location_id == boundary.frontier_location_id
        assert route.destination_location_id is None


def test_hidden_routes_are_marked_not_publicly_known_and_secret(db_session):
    found_hidden = False
    for seed in range(20):
        campaign = create_campaign(db_session, f"Rota Oculta {seed}", world_seed=seed)
        region, _village = seed_initial_region(db_session, campaign.id)
        boundary = create_regional_boundary(db_session, campaign.id, region.id)
        routes = get_boundary_routes(db_session, boundary.id)

        if len(routes) == 3:
            found_hidden = True
            hidden = routes[2]
            assert hidden.is_publicly_known is False

            fact = (
                db_session.query(KnowledgeFact)
                .filter(KnowledgeFact.fact_key == hidden.knowledge_fact_key)
                .one()
            )
            assert fact.is_secret is True

    assert found_hidden


def test_no_knower_is_granted_route_knowledge_at_generation_time(db_session):
    campaign = create_campaign(db_session, "Ninguem Sabe Ainda", world_seed=12)
    region, _village = seed_initial_region(db_session, campaign.id)

    boundary = create_regional_boundary(db_session, campaign.id, region.id)
    routes = get_boundary_routes(db_session, boundary.id)

    for route in routes:
        fact = db_session.query(KnowledgeFact).filter(KnowledgeFact.fact_key == route.knowledge_fact_key).one()
        knowers = db_session.query(KnowledgeKnower).filter(KnowledgeKnower.fact_id == fact.id).all()
        assert knowers == []


def test_boundary_routes_are_deterministic_per_seed(db_session):
    campaign_a = create_campaign(db_session, "Determinismo Rota A", world_seed=77)
    region_a, _village_a = seed_initial_region(db_session, campaign_a.id)
    boundary_a = create_regional_boundary(db_session, campaign_a.id, region_a.id)
    routes_a = get_boundary_routes(db_session, boundary_a.id)

    campaign_b = create_campaign(db_session, "Determinismo Rota B", world_seed=77)
    region_b, _village_b = seed_initial_region(db_session, campaign_b.id)
    boundary_b = create_regional_boundary(db_session, campaign_b.id, region_b.id)
    routes_b = get_boundary_routes(db_session, boundary_b.id)

    assert [(r.name, r.estimated_distance, r.danger_hint) for r in routes_a] == [
        (r.name, r.estimated_distance, r.danger_hint) for r in routes_b
    ]
