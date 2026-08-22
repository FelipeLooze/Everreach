"""Phase 16Q — Cross-Region World Connections.

Once a neighboring Region exists, this is the one place an actual,
walkable LocationConnection gets created between it and the Boundary
that borders it — reusing app.game.world.region_content.connect_locations,
the exact primitive every other road/path in Everreach already uses.
No new travel mechanic: once this runs, app.game.travel.service.move_character
works across the border exactly like it works anywhere else, because it
IS the same LocationConnection graph.

Only one route becomes a real, traversable LocationConnection: every
BoundaryRoute for this boundary currently shares the same
origin_location_id (the boundary's own frontier Location, 16B/16D), and
app.game.travel.service.find_connection assumes at most one active
connection per (from, to) pair — creating one LocationConnection per
route between the identical pair would make all but one of them
invisible to real travel anyway (find_connection's own `.first()`).
The safest publicly known route (lowest danger_hint) is picked as the
real edge, using its own estimated_distance/danger_hint so its 16D-time
promise is actually load-bearing rather than decorative. Other routes
keep destination_location_id unset — they remain real, discoverable,
narratively distinct BoundaryRoute rows, just not yet each a distinct
walkable graph edge. Giving every route its own physical origin
Location (so each could get its own real edge) is a natural follow-up,
not done here to keep this subphase's change small and honest about
what it actually delivers.
"""

import random

from sqlalchemy.orm import Session

from app.core.enums import ConnectionType
from app.db.models.boundary_route import BoundaryRoute
from app.db.models.location import Location
from app.db.models.regional_boundary import RegionalBoundary
from app.db.models.region import Region
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.world.boundaries import get_boundary_routes
from app.game.world.generation import derive_seed
from app.game.world.generator import roll_compass_direction_pair
from app.game.world.region_content import connect_locations


def _neighbor_entry_location(db: Session, neighbor_region_id: str) -> Location:
    """The neighboring Region's own first subregion's major settlement —
    the natural "you have arrived" landing point, mirroring how the
    starting Region's own anchor village plays the same role locally."""
    first_subregion = (
        db.query(Subregion)
        .filter(Subregion.region_id == neighbor_region_id, Subregion.order_index == 0)
        .one()
    )
    return (
        db.query(Location)
        .join(Settlement, Settlement.location_id == Location.id)
        .filter(Location.subregion_id == first_subregion.id)
        .order_by(Settlement.population_tier.desc())
        .first()
    )


def connect_boundary_to_neighbor_region(
    db: Session,
    boundary: RegionalBoundary,
    neighbor_region: Region,
) -> Location:
    """Wires every one of the boundary's routes to a real
    LocationConnection pair reaching into neighbor_region, and marks the
    boundary as having a materialized destination. Returns the entry
    Location on the neighbor's side."""
    entry_location = _neighbor_entry_location(db, neighbor_region.id)

    routes = get_boundary_routes(db, boundary.id)
    public_routes = [route for route in routes if route.is_publicly_known]
    primary_route = min(public_routes or routes, key=lambda route: route.danger_hint)

    rng = random.Random(derive_seed(boundary.generation_seed or 0, "cross_region_connection"))
    forward, back = roll_compass_direction_pair(rng)
    connect_locations(
        db,
        db.get(Location, primary_route.origin_location_id),
        entry_location,
        forward,
        back,
        distance=primary_route.estimated_distance,
        danger=primary_route.danger_hint,
        ctype=ConnectionType.ROAD,
    )
    primary_route.destination_location_id = entry_location.id

    boundary.destination_region_id = neighbor_region.id
    db.flush()

    return entry_location
