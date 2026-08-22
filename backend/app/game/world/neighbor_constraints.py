"""Phase 16H — Neighbor Region Constraints.

A newly generated Region must respect established border facts (spec):
the terrain a boundary represents doesn't just vanish on the far side,
a publicly known route doesn't just stop existing, a barrier's own
hazards are plausible reasons for something similar nearby. This module
assembles that into one structured, read-only package a future
generator (16I+) consumes — never persisted, always derived fresh from
whatever the boundary/barriers/routes already say, since those are
themselves the authoritative source (no separate "constraints" table to
keep in sync).

Hidden routes are deliberately excluded — nobody publicly knows they
exist, so nothing about them should constrain what the far side looks
like; that would leak world-truth the generator has no business
assuming. known_imported_goods stays empty until 16N (Economy & Trade
Relations) actually establishes cross-region trade — inventing goods
here before that subphase exists would just be prose no consumer reads.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import BoundaryBarrierCategory
from app.db.models.location import Location
from app.db.models.regional_boundary import RegionalBoundary
from app.game.world.boundaries import get_boundary_barriers, get_boundary_routes


@dataclass
class NeighborRegionConstraints:
    border_side: str
    required_geography: str
    continuing_geography: list[str] = field(default_factory=list)
    known_routes: list[str] = field(default_factory=list)
    known_dangers: list[str] = field(default_factory=list)
    known_political_notes: list[str] = field(default_factory=list)
    known_historical_relationship: str = ""
    known_imported_goods: list[str] = field(default_factory=list)


def build_neighbor_region_constraints(db: Session, boundary: RegionalBoundary) -> NeighborRegionConstraints:
    barriers = get_boundary_barriers(db, boundary.id)
    routes = get_boundary_routes(db, boundary.id)

    continuing_geography = [
        location.name
        for location in db.query(Location)
        .filter(
            Location.subregion_id == boundary.anchor_subregion_id,
            Location.parent_location_id.is_(None),
            Location.id != boundary.frontier_location_id,
        )
        .all()
    ]

    known_routes = [route.name for route in routes if route.is_publicly_known]

    known_dangers = [
        f"{barrier.name} ({barrier.category})"
        for barrier in barriers
        if barrier.category != BoundaryBarrierCategory.POLITICAL.value
    ]

    known_political_notes = [
        barrier.name for barrier in barriers if barrier.category == BoundaryBarrierCategory.POLITICAL.value
    ] + [route.political_control for route in routes if route.political_control]

    has_political_tension = len(known_political_notes) > 0
    known_historical_relationship = (
        "Tensão política já documentada na fronteira."
        if has_political_tension
        else "Nenhum histórico de contato documentado até o momento."
    )

    return NeighborRegionConstraints(
        border_side=boundary.boundary_side,
        required_geography=boundary.name,
        continuing_geography=continuing_geography,
        known_routes=known_routes,
        known_dangers=known_dangers,
        known_political_notes=known_political_notes,
        known_historical_relationship=known_historical_relationship,
        known_imported_goods=[],
    )
