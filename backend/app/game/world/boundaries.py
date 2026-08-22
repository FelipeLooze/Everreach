"""Phase 16B — Regional Boundary Foundation.

A RegionalBoundary represents the world conditions separating a
materialized Region from whatever lies beyond it — not a map line, not a
level gate (spec's "REGION BORDER = WORLD PROBLEM"). This module creates
the boundary itself plus the one real, ordinary Location that anchors it
in the world: a "frontier" the protagonist (or anyone else) can actually
walk to using the existing travel graph, exactly like any other Location.

What makes crossing hard (16C barriers) and what routes exist through it
(16D routes) are deliberately separate concerns, added in later
subphases — this module only establishes that the edge itself exists and
is reachable.
"""

import random

from sqlalchemy.orm import Session

from app.db.models.location import Location, LocationConnection
from app.db.models.regional_boundary import RegionalBoundary
from app.db.models.region import Region
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.world.content_pools import BOUNDARY_NAME_POOL_BY_BIOME
from app.game.world.generation import derive_seed
from app.game.world.generator import (
    POI_DISTANCE_RANGE,
    poi_connection_danger,
    roll_compass_direction_pair,
)

FRONTIER_LOCATION_TYPE = "region_frontier"


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

    return boundary


def get_regional_boundaries(db: Session, campaign_id: str, source_region_id: str) -> list[RegionalBoundary]:
    return (
        db.query(RegionalBoundary)
        .filter(
            RegionalBoundary.campaign_id == campaign_id,
            RegionalBoundary.source_region_id == source_region_id,
        )
        .all()
    )
