"""Phase 20M — Travel Planning Integration.

"Run pathfinding only over routes available in the character's map
knowledge" (spec, mandatory) — plan_known_route's graph IS
get_map_view's own `routes` list, already gated by
CharacterConnectionDiscovery (see app.game.map.view's 20F docstring).
There is no second, privileged query against the authoritative
LocationConnection table here: this module cannot leak an unknown
route even by accident, because the graph it searches never contains
one to begin with.

This is planning/presentation only. Nothing here moves a character or
consumes time/stamina — the real journey remains
app.game.travel.service.move_character's job, subject to the same
incidents, encumbrance, and risk it has always been subject to. A
returned RoutePlan is not a promise; it is what the map can currently
tell the player about a route they already know.
"""
import heapq
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.game.map.view import MapViewRoute, get_map_view
from app.game.travel.service import BASE_MINUTES_PER_DISTANCE, DEFAULT_TRAVEL_SPEED_MULTIPLIER


@dataclass(frozen=True)
class RoutePlanSegment:
    from_location_id: str
    to_location_id: str
    direction: str | None
    connection_type: str
    distance: float
    danger: int


@dataclass(frozen=True)
class RoutePlan:
    from_location_id: str
    to_location_id: str
    segments: list[RoutePlanSegment] = field(default_factory=list)
    total_distance: float = 0.0
    estimated_minutes: int = 0
    max_danger: int = 0


def _estimated_minutes(route: MapViewRoute) -> int:
    raw_minutes = (
        BASE_MINUTES_PER_DISTANCE * route.distance * route.travel_time_modifier / DEFAULT_TRAVEL_SPEED_MULTIPLIER
    )
    return max(1, round(raw_minutes))


def plan_known_route(
    db: Session,
    campaign_id: str,
    character_id: str,
    from_location_id: str,
    to_location_id: str,
) -> RoutePlan | None:
    """None means "no known route" (spec's own required phrasing) —
    either an endpoint isn't even in the character's Map View, or no
    chain of known connections links them. Never falls back to the
    authoritative graph to fill the gap."""
    view = get_map_view(db, campaign_id, character_id)
    known_location_ids = {location.id for location in view.locations}
    if from_location_id not in known_location_ids or to_location_id not in known_location_ids:
        return None

    if from_location_id == to_location_id:
        return RoutePlan(from_location_id=from_location_id, to_location_id=to_location_id)

    adjacency: dict[str, list[MapViewRoute]] = {}
    for route in view.routes:
        adjacency.setdefault(route.from_location_id, []).append(route)

    best_distance: dict[str, float] = {from_location_id: 0.0}
    incoming_route: dict[str, MapViewRoute] = {}
    frontier: list[tuple[float, str]] = [(0.0, from_location_id)]
    settled: set[str] = set()

    while frontier:
        distance, location_id = heapq.heappop(frontier)
        if location_id in settled:
            continue
        settled.add(location_id)
        if location_id == to_location_id:
            break
        for route in adjacency.get(location_id, []):
            candidate_distance = distance + route.distance
            if route.to_location_id not in best_distance or candidate_distance < best_distance[route.to_location_id]:
                best_distance[route.to_location_id] = candidate_distance
                incoming_route[route.to_location_id] = route
                heapq.heappush(frontier, (candidate_distance, route.to_location_id))

    if to_location_id not in best_distance:
        return None

    segments: list[RoutePlanSegment] = []
    current = to_location_id
    while current != from_location_id:
        route = incoming_route[current]
        segments.append(
            RoutePlanSegment(
                from_location_id=route.from_location_id,
                to_location_id=route.to_location_id,
                direction=route.direction,
                connection_type=route.connection_type,
                distance=route.distance,
                danger=route.danger,
            )
        )
        current = route.from_location_id
    segments.reverse()

    used_routes = [incoming_route[segment.to_location_id] for segment in segments]

    return RoutePlan(
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        segments=segments,
        total_distance=sum(segment.distance for segment in segments),
        estimated_minutes=sum(_estimated_minutes(route) for route in used_routes),
        max_danger=max((segment.danger for segment in segments), default=0),
    )
