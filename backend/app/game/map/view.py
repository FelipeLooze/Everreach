"""The player's map: a projection of world geography through what the
character knows — never a second copy of the world.

One source decides what appears (simplification, 2026-10-23): the
character's discovery tables (CharacterLocationDiscovery for places,
CharacterConnectionDiscovery for routes), which every way of learning a
place now writes — travel, exploration, rumors, shared routes, expeditions,
what NPCs tell. Physical maps the character owns are the one other source:
an item holding a frozen snapshot of past knowledge, which may go stale.

- Precision comes from the discovery status: DISCOVERED (heard of, seen,
  told) is APPROXIMATE, VISITED is PRECISE. Exact coordinates only ship
  when PRECISE.
- The name shows when the character knows it (visited, told, or a NAME
  grant); hidden identities follow location_display_name.
- scope ("world" | "region:{id}" | "subregion:{id}" | "settlement:{id}")
  and the LOD filters (detail_level="far", viewport) narrow the list;
  routes and annotations follow the locations that survive.
- position_* is the character's own location, never more precise than any
  other entry.

The richer per-aspect/precision geographic facts (Phase 17) remain what
NPCs and organizations know and can share; the player's map no longer
reads them through parallel paths.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.character import Character
from app.db.models.item import ItemInstance
from app.db.models.location import Location
from app.db.models.map import Map
from app.db.models.map_annotation import MapAnnotation
from app.db.models.region import Region
from app.game.discovery.service import get_location_discovery, location_display_name
from app.game.knowledge.geography import geographic_fact_key, precision_rank
from app.game.knowledge.map_reliability import find_outdated_map_aspects
from app.game.knowledge.maps import map_content
from app.game.knowledge.service import explicitly_knows_name
from app.game.map.service import known_map
from app.game.npcs.service import knows

_POSITION_ASPECTS = (
    GeographicKnowledgeAspect.ROUTE,
    GeographicKnowledgeAspect.DISTANCE,
    GeographicKnowledgeAspect.DIRECTION,
)

_DISCOVERY_STATUS_PRECISION: dict[DiscoveryStatus, GeographicPrecision] = {
    DiscoveryStatus.DISCOVERED: GeographicPrecision.APPROXIMATE,
    DiscoveryStatus.VISITED: GeographicPrecision.PRECISE,
}
_PROVENANCE = {
    DiscoveryStatus.DISCOVERED: "conhecido, não visitado",
    DiscoveryStatus.VISITED: "presença física",
}


@dataclass(frozen=True)
class MapViewLocation:
    id: str
    region_id: str
    subregion_id: str | None
    parent_location_id: str | None
    type: str
    name: str | None
    precision: str | None
    x: int | None
    y: int | None
    discovery_status: str
    source: str = "discovery"
    stale: bool = False
    provenance: str | None = None
    materialization_tier: int = 1
    known_aspects: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MapViewRegion:
    id: str
    name: str | None
    discovery_status: str


@dataclass(frozen=True)
class MapViewRoute:
    from_location_id: str
    to_location_id: str
    direction: str | None
    connection_type: str
    distance: float
    danger: int
    travel_time_modifier: float = 1.0


@dataclass(frozen=True)
class MapViewAnnotation:
    id: str
    location_id: str
    text: str
    created_at: str


@dataclass(frozen=True)
class MapViewData:
    campaign_id: str
    character_id: str
    scope: str | None
    regions: list[MapViewRegion] = field(default_factory=list)
    locations: list[MapViewLocation] = field(default_factory=list)
    routes: list[MapViewRoute] = field(default_factory=list)
    annotations: list[MapViewAnnotation] = field(default_factory=list)
    position_location_id: str | None = None
    position_precision: str | None = None


def _knows_name_aspect(
    db: Session, campaign_id: str, character_id: str, location_id: str
) -> bool:
    fact_key = geographic_fact_key("location", location_id, GeographicKnowledgeAspect.NAME)
    return knows(db, KnowerType.PLAYER, character_id, fact_key, campaign_id)


def _owned_maps_by_location(db: Session, character_id: str) -> dict[str, list[Map]]:
    """Every "location"-subject physical Map the character currently
    owns, grouped by the entity it covers. A map that changed hands or
    was lost stops counting (same ItemInstance-ownership convention as
    app.game.knowledge.maps.character_maps_covering)."""
    map_rows = (
        db.query(Map)
        .join(ItemInstance, ItemInstance.id == Map.item_instance_id)
        .filter(
            ItemInstance.owner_type == "CHARACTER",
            ItemInstance.owner_ref == character_id,
            Map.subject_kind == "location",
        )
        .all()
    )
    by_location: dict[str, list[Map]] = {}
    for map_row in map_rows:
        by_location.setdefault(map_row.entity_id, []).append(map_row)
    return by_location


def _build_map_view_location_from_maps(
    db: Session,
    campaign_id: str,
    location: Location,
    discovery_status: DiscoveryStatus,
    map_rows: list[Map],
) -> MapViewLocation:
    contents = [map_content(map_row) for map_row in map_rows]
    stale = any(find_outdated_map_aspects(db, campaign_id, map_row) for map_row in map_rows)
    all_aspects = [aspect for content in contents for aspect in content["aspects"]]
    known_aspect_values = {aspect["aspect"] for aspect in all_aspects}
    known_aspect_values.add(GeographicKnowledgeAspect.EXISTENCE.value)
    name_known = GeographicKnowledgeAspect.NAME.value in known_aspect_values

    position_aspect_values = {aspect.value for aspect in _POSITION_ASPECTS}
    best_precision: GeographicPrecision | None = None
    for aspect in all_aspects:
        if aspect["aspect"] not in position_aspect_values or aspect["precision"] is None:
            continue
        precision = GeographicPrecision(aspect["precision"])
        if best_precision is None or precision_rank(precision) > precision_rank(best_precision):
            best_precision = precision
    exact_position_known = best_precision == GeographicPrecision.PRECISE

    return MapViewLocation(
        id=location.id,
        region_id=location.region_id,
        subregion_id=location.subregion_id,
        parent_location_id=location.parent_location_id,
        type=location.type,
        name=location.name if name_known else None,
        precision=best_precision.value if best_precision is not None else None,
        x=location.x if exact_position_known else None,
        y=location.y if exact_position_known else None,
        discovery_status=discovery_status.value,
        source="map",
        stale=stale,
        provenance="mapa físico",
        materialization_tier=location.materialization_tier,
        known_aspects=sorted(known_aspect_values),
    )


def _build_map_view_location(
    db: Session,
    campaign_id: str,
    character_id: str,
    location: Location,
    discovery_status: DiscoveryStatus,
) -> MapViewLocation:
    precision = _DISCOVERY_STATUS_PRECISION[discovery_status]
    canonical_name_known = _knows_name_aspect(
        db, campaign_id, character_id, location.id
    ) or explicitly_knows_name(db, campaign_id, KnowerType.PLAYER, character_id, location.name)
    discovery = get_location_discovery(db, character_id, location.id)
    display_name = location_display_name(
        location, discovery, canonical_name_known=canonical_name_known
    )
    exact_position_known = precision == GeographicPrecision.PRECISE
    known_aspects = {GeographicKnowledgeAspect.EXISTENCE.value}
    if display_name == location.name:
        known_aspects.add(GeographicKnowledgeAspect.NAME.value)

    return MapViewLocation(
        id=location.id,
        region_id=location.region_id,
        subregion_id=location.subregion_id,
        parent_location_id=location.parent_location_id,
        type=location.type,
        name=display_name,
        precision=precision.value,
        x=location.x if exact_position_known else None,
        y=location.y if exact_position_known else None,
        discovery_status=discovery_status.value,
        source="discovery",
        provenance=_PROVENANCE[discovery_status],
        materialization_tier=location.materialization_tier,
        known_aspects=sorted(known_aspects),
    )


def _apply_scope(
    regions: list[MapViewRegion],
    locations: list[MapViewLocation],
    scope: str | None,
) -> tuple[list[MapViewRegion], list[MapViewLocation]]:
    if scope is None:
        return regions, locations

    if scope == "world":
        return regions, []

    if ":" in scope:
        level, target_id = scope.split(":", 1)
        if level == "region":
            if target_id not in {region.id for region in regions}:
                return [], []
            return (
                [region for region in regions if region.id == target_id],
                [location for location in locations if location.region_id == target_id],
            )
        if level == "subregion":
            known_subregion_ids = {
                location.subregion_id for location in locations if location.subregion_id is not None
            }
            if target_id not in known_subregion_ids:
                return [], []
            scoped_locations = [location for location in locations if location.subregion_id == target_id]
            scoped_region_ids = {location.region_id for location in scoped_locations}
            return (
                [region for region in regions if region.id in scoped_region_ids],
                scoped_locations,
            )
        if level == "settlement":
            scoped_locations = [
                location for location in locations if location.parent_location_id == target_id
            ]
            if not scoped_locations:
                return [], []
            scoped_region_ids = {location.region_id for location in scoped_locations}
            return (
                [region for region in regions if region.id in scoped_region_ids],
                scoped_locations,
            )

    # Unrecognized scope — never fall back to the unscoped view.
    return [], []


def _apply_lod(
    locations: list[MapViewLocation],
    detail_level: str | None,
    viewport: tuple[float, float, float, float] | None,
) -> list[MapViewLocation]:
    result = locations
    if detail_level == "far":
        result = [location for location in result if location.materialization_tier <= 1]
    if viewport is not None:
        min_x, min_y, max_x, max_y = viewport
        result = [
            location
            for location in result
            if location.x is None
            or location.y is None
            or (min_x <= location.x <= max_x and min_y <= location.y <= max_y)
        ]
    return result


def get_map_view(
    db: Session,
    campaign_id: str,
    character_id: str,
    *,
    scope: str | None = None,
    detail_level: str | None = None,
    viewport: tuple[float, float, float, float] | None = None,
    visited_only: bool = False,
) -> MapViewData:
    data = known_map(db, campaign_id, character_id, visited_only=visited_only)

    locations: list[MapViewLocation] = [
        _build_map_view_location(
            db, campaign_id, character_id, location, DiscoveryStatus(data["location_discovery"][location.id])
        )
        for location in data["locations"]
    ]
    regions_by_id = {region.id: region for region in data["regions"]}

    # Owned physical maps: places known only from a map the character holds.
    included_location_ids = {location.id for location in locations}
    maps_by_location = _owned_maps_by_location(db, character_id)
    map_only_ids = set(maps_by_location) - included_location_ids if not visited_only else set()
    if map_only_ids:
        map_only_locations = (
            db.query(Location)
            .join(Region, Region.id == Location.region_id)
            .filter(Location.id.in_(map_only_ids), Region.campaign_id == campaign_id)
            .order_by(Location.name)
            .all()
        )
        for location in map_only_locations:
            locations.append(
                _build_map_view_location_from_maps(
                    db, campaign_id, location, DiscoveryStatus.DISCOVERED, maps_by_location[location.id]
                )
            )
            if location.region_id not in regions_by_id:
                region = db.get(Region, location.region_id)
                if region is not None:
                    regions_by_id[region.id] = region

    position_location_id: str | None = None
    position_precision: str | None = None
    character = db.get(Character, character_id)
    if character is not None and character.location_id is not None:
        current_location_entry = next(
            (location for location in locations if location.id == character.location_id), None
        )
        if current_location_entry is not None:
            position_location_id = current_location_entry.id
            position_precision = current_location_entry.precision

    regions = []
    for region in regions_by_id.values():
        name_known = explicitly_knows_name(
            db, campaign_id, KnowerType.PLAYER, character_id, region.name
        )
        regions.append(
            MapViewRegion(
                id=region.id,
                name=region.name if name_known else None,
                discovery_status=region.discovery_status,
            )
        )
    regions.sort(key=lambda region: region.id)

    regions, locations = _apply_scope(regions, locations, scope)
    locations = _apply_lod(locations, detail_level, viewport)

    visible_location_ids = {location.id for location in locations}
    routes = [
        MapViewRoute(
            from_location_id=connection.from_location_id,
            to_location_id=connection.to_location_id,
            direction=connection.direction,
            connection_type=connection.connection_type,
            distance=connection.distance,
            danger=connection.danger,
            travel_time_modifier=connection.travel_time_modifier,
        )
        for connection in data["connections"]
        if connection.from_location_id in visible_location_ids
        and connection.to_location_id in visible_location_ids
    ]

    annotation_rows = (
        db.query(MapAnnotation)
        .filter(
            MapAnnotation.campaign_id == campaign_id,
            MapAnnotation.character_id == character_id,
            MapAnnotation.location_id.in_(visible_location_ids),
        )
        .order_by(MapAnnotation.created_at)
        .all()
    ) if visible_location_ids else []
    annotations = [
        MapViewAnnotation(
            id=row.id, location_id=row.location_id, text=row.text, created_at=row.created_at.isoformat()
        )
        for row in annotation_rows
    ]

    return MapViewData(
        campaign_id=campaign_id,
        character_id=character_id,
        scope=scope,
        regions=regions,
        locations=locations,
        routes=routes,
        annotations=annotations,
        position_location_id=position_location_id,
        position_precision=position_precision,
    )
