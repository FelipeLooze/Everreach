"""Phase 16H — Neighbor Region Constraints."""

from app.game.world.boundaries import create_regional_boundary, get_boundary_routes
from app.game.world.neighbor_constraints import build_neighbor_region_constraints
from app.game.world.seed import create_campaign, seed_initial_region


def test_constraints_reflect_the_boundary_itself(db_session):
    campaign = create_campaign(db_session, "Restricoes", world_seed=13)
    region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, region.id)

    constraints = build_neighbor_region_constraints(db_session, boundary)

    assert constraints.border_side == boundary.boundary_side
    assert constraints.required_geography == boundary.name
    assert len(constraints.continuing_geography) >= 1


def test_only_publicly_known_routes_are_listed(db_session):
    campaign = create_campaign(db_session, "Rotas Publicas", world_seed=14)
    region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, region.id)
    routes = get_boundary_routes(db_session, boundary.id)

    constraints = build_neighbor_region_constraints(db_session, boundary)

    public_names = {r.name for r in routes if r.is_publicly_known}
    hidden_names = {r.name for r in routes if not r.is_publicly_known}

    assert set(constraints.known_routes) == public_names
    assert not (hidden_names & set(constraints.known_routes))


def test_known_dangers_never_include_political_barriers(db_session):
    from app.core.enums import BoundaryBarrierCategory
    from app.game.world.boundaries import get_boundary_barriers

    found_political_case = False
    for seed in range(30):
        campaign = create_campaign(db_session, f"Sem Politica Em Perigos {seed}", world_seed=seed)
        region, _village = seed_initial_region(db_session, campaign.id)
        boundary = create_regional_boundary(db_session, campaign.id, region.id)
        barriers = get_boundary_barriers(db_session, boundary.id)

        political = [b for b in barriers if b.category == BoundaryBarrierCategory.POLITICAL.value]
        if not political:
            continue
        found_political_case = True

        constraints = build_neighbor_region_constraints(db_session, boundary)
        for note in political:
            assert not any(note.name in danger for danger in constraints.known_dangers)
            assert note.name in constraints.known_political_notes

    assert found_political_case


def test_known_imported_goods_is_deliberately_empty_until_16n(db_session):
    campaign = create_campaign(db_session, "Sem Bens Importados Ainda", world_seed=15)
    region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, region.id)

    constraints = build_neighbor_region_constraints(db_session, boundary)

    assert constraints.known_imported_goods == []
