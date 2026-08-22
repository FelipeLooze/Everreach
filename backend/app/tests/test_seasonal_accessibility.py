"""Phase 16E — Seasonal & Temporal Accessibility."""

import pytest

from app.core.enums import RouteAccessibility, Season
from app.db.models.boundary_route import BoundaryRoute
from app.game.time.clock import advance_world_time, current_season, season_for_month
from app.game.world.boundaries import (
    create_regional_boundary,
    current_route_accessibility,
    get_boundary_routes,
    route_accessibility_for_season,
)
from app.game.world.seed import create_campaign, seed_initial_region


@pytest.mark.parametrize(
    "month,expected",
    [
        (1, Season.WINTER), (2, Season.WINTER), (12, Season.WINTER),
        (3, Season.SPRING), (4, Season.SPRING), (5, Season.SPRING),
        (6, Season.SUMMER), (7, Season.SUMMER), (8, Season.SUMMER),
        (9, Season.AUTUMN), (10, Season.AUTUMN), (11, Season.AUTUMN),
    ],
)
def test_season_for_month_covers_the_full_calendar(month, expected):
    assert season_for_month(month) == expected


def test_route_in_its_own_harsh_season_is_never_fully_open():
    route = BoundaryRoute(
        boundary_id="bound_x",
        origin_location_id="loc_x",
        name="Rota de Teste",
        harsh_season=Season.WINTER.value,
        danger_hint=3,
    )
    assert route_accessibility_for_season(route, Season.WINTER.value) == RouteAccessibility.RISKY.value


def test_severe_route_in_its_harsh_season_is_nearly_impassable():
    route = BoundaryRoute(
        boundary_id="bound_x",
        origin_location_id="loc_x",
        name="Rota Severa",
        harsh_season=Season.WINTER.value,
        danger_hint=9,
    )
    assert route_accessibility_for_season(route, Season.WINTER.value) == RouteAccessibility.NEARLY_IMPASSABLE.value


def test_mild_route_in_opposite_season_is_open():
    route = BoundaryRoute(
        boundary_id="bound_x",
        origin_location_id="loc_x",
        name="Rota Tranquila",
        harsh_season=Season.WINTER.value,
        danger_hint=2,
    )
    assert route_accessibility_for_season(route, Season.SUMMER.value) == RouteAccessibility.OPEN.value


def test_severe_route_is_never_open_even_in_the_opposite_season():
    route = BoundaryRoute(
        boundary_id="bound_x",
        origin_location_id="loc_x",
        name="Rota Sempre Perigosa",
        harsh_season=Season.WINTER.value,
        danger_hint=9,
    )
    assert route_accessibility_for_season(route, Season.SUMMER.value) == RouteAccessibility.RISKY.value


def test_adjacent_season_is_always_risky():
    route = BoundaryRoute(
        boundary_id="bound_x",
        origin_location_id="loc_x",
        name="Rota Adjacente",
        harsh_season=Season.WINTER.value,
        danger_hint=1,
    )
    assert route_accessibility_for_season(route, Season.SPRING.value) == RouteAccessibility.RISKY.value
    assert route_accessibility_for_season(route, Season.AUTUMN.value) == RouteAccessibility.RISKY.value


def test_current_route_accessibility_tracks_world_time_advancing(db_session):
    campaign = create_campaign(db_session, "Acessibilidade Sazonal", world_seed=44)
    region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, region.id)
    route = get_boundary_routes(db_session, boundary.id)[0]

    before = current_season(db_session, campaign.id)
    before_accessibility = current_route_accessibility(db_session, campaign.id, route)
    assert before_accessibility == route_accessibility_for_season(route, before.value)

    # Advance a full year in three-month jumps and confirm accessibility
    # always matches whatever season the clock says right now — never a
    # value frozen at generation time.
    for _ in range(4):
        advance_world_time(db_session, campaign.id, 60 * 24 * 30 * 3)
        season_now = current_season(db_session, campaign.id)
        assert current_route_accessibility(db_session, campaign.id, route) == route_accessibility_for_season(
            route, season_now.value
        )
