"""Phase 16B/16C/16D/16E — Regional Boundary Foundation, Boundary
Barriers, Cross-Region Routes & Seasonal Accessibility.

A RegionalBoundary represents the world conditions separating a
materialized Region from whatever lies beyond it — not a map line, not a
level gate (spec's "REGION BORDER = WORLD PROBLEM"). create_regional_boundary
creates the boundary itself, the one real Location that anchors it in the
world (a "frontier" reachable through the ordinary travel graph like any
other Location), its BoundaryBarrier rows (16C) — what actually makes it
hard to cross — and its BoundaryRoute rows (16D) — the possible ways
through, "BOUNDARY != ROUTE" kept as separate tables throughout.

route_accessibility_for_season (16E) is the one place accessibility is
ever computed — always derived from a route + the current in-world
season, never stored as a boolean (spec).
"""

import random

from sqlalchemy.orm import Session

from app.core.enums import RouteAccessibility, Season
from app.db.models.boundary_barrier import BoundaryBarrier
from app.db.models.boundary_route import BoundaryRoute
from app.db.models.knowledge import KnowledgeFact
from app.db.models.location import Location, LocationConnection
from app.db.models.regional_boundary import RegionalBoundary
from app.db.models.region import Region
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.time.clock import current_season
from app.game.world.content_pools import BOUNDARY_NAME_POOL_BY_BIOME
from app.game.world.generation import derive_seed
from app.game.world.generator import (
    POI_DISTANCE_RANGE,
    generate_boundary_barriers,
    generate_boundary_routes,
    poi_connection_danger,
    roll_compass_direction_pair,
)

FRONTIER_LOCATION_TYPE = "region_frontier"

_SEASON_ORDER = [Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER]
_SEVERE_DANGER_THRESHOLD = 8


def _season_distance(a: str, b: str) -> int:
    ia, ib = _SEASON_ORDER.index(Season(a)), _SEASON_ORDER.index(Season(b))
    diff = abs(ia - ib)
    return min(diff, len(_SEASON_ORDER) - diff)


def route_accessibility_for_season(route: BoundaryRoute, season: str) -> str:
    """OPEN/RISKY/NEARLY_IMPASSABLE — always computed fresh, never read
    from a stored field. A route already severe (high danger_hint) is
    never fully OPEN even in its best season."""
    distance = _season_distance(route.harsh_season, season)
    severe = route.danger_hint >= _SEVERE_DANGER_THRESHOLD

    if distance == 0:
        return RouteAccessibility.NEARLY_IMPASSABLE.value if severe else RouteAccessibility.RISKY.value
    if distance == 1:
        return RouteAccessibility.RISKY.value
    return RouteAccessibility.RISKY.value if severe else RouteAccessibility.OPEN.value


def current_route_accessibility(db: Session, campaign_id: str, route: BoundaryRoute) -> str:
    return route_accessibility_for_season(route, current_season(db, campaign_id).value)


def _outermost_subregion(db: Session, region_id: str) -> Subregion:
    """The subregion farthest from the anchor in the region's own
    settlement chain (see app.game.world.seed's ordered_majors) — the
    natural "edge of what's currently mapped", since Phase 15 subregions
    already form one chain per region rather than a 2D map."""
    return (
        db.query(Subregion)
        .filter(Subregion.region_id == region_id)
        .order_by(Subregion.order_index.desc())
        .first()
    )


def _anchor_location_for_subregion(db: Session, subregion_id: str) -> Location:
    """The subregion's own major settlement (Phase 15F: exactly one per
    non-anchor subregion) — a deterministic, always-present choice to
    hang the frontier connection off of, so two campaigns sharing a
    world_seed always pick the same anchor."""
    return (
        db.query(Location)
        .join(Settlement, Settlement.location_id == Location.id)
        .filter(Location.subregion_id == subregion_id)
        .order_by(Settlement.population_tier.desc())
        .first()
    )


def create_regional_boundary(
    db: Session,
    campaign_id: str,
    source_region_id: str,
    *,
    boundary_side: str = "",
    anchor_subregion_id: str | None = None,
) -> RegionalBoundary:
    """
    Establish a new RegionalBoundary on source_region_id: picks (or uses
    the given) anchor Subregion, materializes a real frontier Location
    there, and connects it into the existing travel graph. destination_region_id
    stays NULL — a later subphase (16I+) fills it in once/if a neighbor is
    actually generated.
    """
    region = db.get(Region, source_region_id)
    if region is None or region.campaign_id != campaign_id:
        raise ValueError(f"Unknown region {source_region_id} for campaign {campaign_id}")

    subregion = (
        db.get(Subregion, anchor_subregion_id)
        if anchor_subregion_id is not None
        else _outermost_subregion(db, source_region_id)
    )
    if subregion is None or subregion.region_id != source_region_id:
        raise ValueError(f"No valid anchor subregion found for region {source_region_id}")

    anchor_location = _anchor_location_for_subregion(db, subregion.id)
    if anchor_location is None:
        raise ValueError(f"Subregion {subregion.id} has no Location to anchor a boundary to")

    boundary_seed = derive_seed(region.generation_seed or 0, f"boundary:{subregion.order_index}")
    rng = random.Random(boundary_seed)

    name_pool = BOUNDARY_NAME_POOL_BY_BIOME.get(str(subregion.biome), BOUNDARY_NAME_POOL_BY_BIOME["FRONTIER"])
    name, description = rng.choice(name_pool)

    if not boundary_side:
        boundary_side, _back = roll_compass_direction_pair(rng)

    frontier_location = Location(
        region_id=source_region_id,
        subregion_id=subregion.id,
        name=name,
        type=FRONTIER_LOCATION_TYPE,
        description=description,
        materialization_tier=1,
    )
    db.add(frontier_location)
    db.flush()

    forward, back = roll_compass_direction_pair(rng)
    low, high = POI_DISTANCE_RANGE
    distance = round(rng.uniform(low, high), 1)
    danger = poi_connection_danger(subregion.danger_level)

    db.add(
        LocationConnection(
            from_location_id=anchor_location.id,
            to_location_id=frontier_location.id,
            direction=forward,
            distance=distance,
            danger=danger,
        )
    )
    db.add(
        LocationConnection(
            from_location_id=frontier_location.id,
            to_location_id=anchor_location.id,
            direction=back,
            distance=distance,
            danger=danger,
        )
    )

    boundary = RegionalBoundary(
        campaign_id=campaign_id,
        source_region_id=source_region_id,
        name=name,
        description=description,
        boundary_side=boundary_side,
        anchor_subregion_id=subregion.id,
        frontier_location_id=frontier_location.id,
        generation_seed=boundary_seed,
    )
    db.add(boundary)
    db.flush()

    for category, barrier_name, barrier_description in generate_boundary_barriers(rng, subregion.biome):
        db.add(
            BoundaryBarrier(
                boundary_id=boundary.id,
                category=category,
                name=barrier_name,
                description=barrier_description,
            )
        )
    db.flush()

    used_names = {row[0] for row in db.query(Location.name).filter(Location.region_id == source_region_id).all()}
    for route_data in generate_boundary_routes(rng, subregion.biome, used_names):
        route = BoundaryRoute(
            boundary_id=boundary.id,
            origin_location_id=frontier_location.id,
            **route_data,
        )
        db.add(route)
        db.flush()

        # World truth always exists the moment a route is generated; who
        # (if anyone) actually knows about it is a separate question left
        # to 16G — nobody is granted this fact here, not even a publicly
        # known route.
        route.knowledge_fact_key = f"boundary_route_exists:{route.id}"
        db.add(
            KnowledgeFact(
                campaign_id=campaign_id,
                subject=f"boundary_route:{route.id}",
                fact_key=route.knowledge_fact_key,
                statement=f"{route.name} é uma possível passagem por {boundary.name}.",
                is_secret=not route.is_publicly_known,
            )
        )
    db.flush()

    return boundary


def get_boundary_barriers(db: Session, boundary_id: str) -> list[BoundaryBarrier]:
    return db.query(BoundaryBarrier).filter(BoundaryBarrier.boundary_id == boundary_id).all()


def get_boundary_routes(db: Session, boundary_id: str) -> list[BoundaryRoute]:
    return db.query(BoundaryRoute).filter(BoundaryRoute.boundary_id == boundary_id).all()


def get_regional_boundaries(db: Session, campaign_id: str, source_region_id: str) -> list[RegionalBoundary]:
    return (
        db.query(RegionalBoundary)
        .filter(
            RegionalBoundary.campaign_id == campaign_id,
            RegionalBoundary.source_region_id == source_region_id,
        )
        .all()
    )
