"""Phase 20A — Player Map Data Contract.

MapViewData is a PROJECTION (Campaign + Character + scope -> player-
visible data), never a second copy of world geography. World geography
stays authoritative in the existing Phase 15/16 Region/Subregion/
Location structures; this module only decides what of it a specific
character is allowed to see, and how precisely.

Real pre-existing gap this module bridges rather than duplicates: two
partially-disconnected geographic knowledge signals exist in the
codebase today —

1. CharacterLocationDiscovery/DiscoveryStatus (Phase 1/15) — set by
   ordinary travel (app.game.travel.service.move_character) via
   app.game.map.service.known_map. This is what actually gets
   populated during normal play; it decides whether a location is
   present in the view AT ALL (never included otherwise — Phase 20's
   own "no omniscient frontend" rule — this module reuses known_map
   for that decision rather than re-deriving it).
2. KnowledgeFact/KnowledgeKnower with GeographicKnowledgeAspect/
   GeographicPrecision (Phase 17A/17B) — set by the exploration/rumor/
   route-sharing/expedition systems. This is the richer, intentional
   signal, but ordinary travel never grants it (move_character has no
   call into app.game.knowledge.geography at all).

Precision here therefore prefers Phase 17's structured grant when one
exists, and falls back to inferring precision from the older
DiscoveryStatus otherwise (RUMORED -> VAGUE, DISCOVERED -> APPROXIMATE,
VISITED/MAPPED -> PRECISE) — a character who only ever walked
somewhere still gets a sensible map, and a character with real Phase 17
geographic knowledge gets the more accurate signal.

Exact coordinates (x/y) are only ever included when the resolved
precision is PRECISE — vague/approximate knowledge never leaks the
authoritative pin merely because the UI would find it convenient.

Phase 20C — Knowledge-Aware Rendering.

Extends 20A/20B to close the exact gap their own audit flagged: a
location known ONLY through a Phase 17 EXISTENCE grant (an NPC saying
"Arven is a large city far south", no travel involved) previously never
appeared in the view at all, because get_map_view relied solely on
known_map's CharacterLocationDiscovery join. _phase17_known_location_ids
below adds that second, independent inclusion path — reusing the exact
fact_key convention app.game.knowledge.geography already established
("location:{id}:existence") rather than inventing a new query surface.

known_aspects on MapViewLocation is the literal "Knowledge Aspects"
section of the spec: EXISTENCE/NAME/DIRECTION/DISTANCE/ROUTE/... are
never collapsed into one boolean — "knows place exists" must not
silently become "knows exact map pin" anywhere in this module.

Phase 20E — Hierarchical Map Levels.

`scope` (already part of the 20A contract, unused until now) becomes a
real filter: "world" (regions only, no location detail — the WORLD
level never drills into geography), "region:{id}" (one Region's known
locations only — the REGION level), "subregion:{id}" (one Subregion's
known locations only). Settlement/district/local-area levels are 20I's
job (independently-discoverable settlement interiors, a different
concern from filtering this same flat knowledge-gated list). An
unrecognized or not-yet-known scope target returns empty data rather
than falling back to the unscoped view — silently ignoring an invalid
scope would let a caller accidentally see more than requested.

Phase 20F — Known Routes & Connections.

"Knowing two places does not imply knowing the route between them" is
already real in this codebase: CharacterConnectionDiscovery (gating
app.game.travel.service.move_character itself) is tracked completely
independently from CharacterLocationDiscovery/location Knowledge —
known_map's own connections query already requires it. routes below
just surfaces that existing, already-correct gate through the Map View
contract instead of re-deriving anything. A route is only ever
included once BOTH its endpoints survive the current scope — so
scoping to one Region or Subregion (20E) automatically scopes routes
too, and the "world" scope (no location detail) yields no routes
either, with zero extra logic.

Phase 20G — Physical Map Integration.

Reuses Phase 17G/17F in full: a physical map is a frozen
CartographicSurvey snapshot (app.game.knowledge.maps.map_content),
taken once, never a live reference back to KnowledgeFact/
KnowledgeKnower. A location covered ONLY by an owned map — no live
CharacterLocationDiscovery row, no live Knowledge grant — now surfaces
too (source="map"), built from that frozen snapshot instead of the
live geography lookups every other path uses; this is the concrete
mechanism behind "MAP DATA != CURRENT WORLD TRUTH" (spec): if the
character's live knowledge is later revoked or the world changes, the
owned map's info does not, because it was never wired to either.
`source` on MapViewLocation ("discovery" / "knowledge" / "map" / "rumor")
is the minimal provenance signal the spec's "MAP SOURCE PROVENANCE"
section asks for; a location known through more than one channel keeps
whichever live signal already included it (discovery/knowledge/map take
precedence — a live signal is always at least as good as a frozen
snapshot of past knowledge, and any of those is stronger than a rumor).

Phase 20H — Rumors & Unconfirmed Locations.

Reuses Phase 17C in full: app.game.knowledge.rumors stores a rumor as
its OWN KnowledgeFact under the ":rumor:{rumor_key}" fact_key
namespace, deliberately never overwriting the canonical aspect fact
for the same (entity, aspect) — "LOGAN HAS HEARD THIS CLAIM" is never
conflated with "THE THING DEFINITELY EXISTS". A location known ONLY
through a rumored EXISTENCE (no canonical Phase 17 grant, no
discovery, no owned map) previously never surfaced at all, because
neither _phase17_known_location_ids' suffix match nor known_map's
discovery join ever look inside the ":rumor:" namespace.
source="rumor" locations deliberately reuse _build_map_view_location's
ordinary live-lookup path rather than a rumor-specific one: since no
canonical aspect grant exists for them, precision naturally falls back
to DiscoveryStatus.RUMORED's own VAGUE mapping and known_aspects stays
{EXISTENCE} — an honest reflection of "a claim was heard", nothing
more, without needing to parse rumor precision/aspects separately.

Phase 20I — Settlement & City Maps.

"Knowing Arven exists does NOT mean knowing its internal layout"
(spec) already holds structurally: every inclusion path in this module
(discovery/knowledge/map/rumor) is per-location, keyed by that exact
Location's own id — a district Location (Phase 15G's
parent_location_id, the same hierarchy Region>Subregion>Settlement>
District>Location>Sublocation>Interior reuses at every level) never
rides in just because its parent settlement is known. Nothing needed
fixing there. What 20I adds is the missing scope LEVEL to view it: a
"settlement:{location_id}" scope (extending 20E's world/region/
subregion) filters to the known child locations of one settlement —
parent_location_id, exposed on MapViewLocation for exactly this.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.item import ItemInstance
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import Location
from app.db.models.map import Map
from app.db.models.region import Region
from app.game.knowledge.geography import (
    geographic_fact_key,
    geographic_knowledge_precision,
    known_geographic_aspects,
    precision_rank,
)
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
    DiscoveryStatus.RUMORED: GeographicPrecision.VAGUE,
    DiscoveryStatus.DISCOVERED: GeographicPrecision.APPROXIMATE,
    DiscoveryStatus.VISITED: GeographicPrecision.PRECISE,
    DiscoveryStatus.MAPPED: GeographicPrecision.PRECISE,
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


@dataclass(frozen=True)
class MapViewData:
    """Deliberately the smallest extensible shape for 20A — a future
    subphase adds fields (rumors, physical-map sources, player
    annotations, LOD/viewport scoping), not restructures this one.

    20B adds `regions` — grouping metadata the interactive frontend needs
    to render locations by region, gated by the same
    explicitly_knows_name convention the old /map route already used.

    20F adds `routes` — see module docstring."""

    campaign_id: str
    character_id: str
    scope: str | None
    regions: list[MapViewRegion] = field(default_factory=list)
    locations: list[MapViewLocation] = field(default_factory=list)
    routes: list[MapViewRoute] = field(default_factory=list)


def _knows_name_aspect(
    db: Session, campaign_id: str, character_id: str, location_id: str
) -> bool:
    fact_key = geographic_fact_key("location", location_id, GeographicKnowledgeAspect.NAME)
    return knows(db, KnowerType.PLAYER, character_id, fact_key, campaign_id)


def _best_known_precision(
    db: Session,
    campaign_id: str,
    character_id: str,
    location: Location,
    discovery_status: DiscoveryStatus,
) -> GeographicPrecision | None:
    best: GeographicPrecision | None = None
    for aspect in _POSITION_ASPECTS:
        precision = geographic_knowledge_precision(
            db, campaign_id, KnowerType.PLAYER, character_id, "location", location.id, aspect
        )
        if precision is not None and (best is None or precision_rank(precision) > precision_rank(best)):
            best = precision
    if best is not None:
        return best
    return _DISCOVERY_STATUS_PRECISION.get(discovery_status)


def _phase17_known_location_ids(db: Session, campaign_id: str, character_id: str) -> set[str]:
    """Locations the character knows EXIST purely through a Phase 17
    Knowledge grant (an NPC report, a rumor, a shared map) — no
    CharacterLocationDiscovery row required. See module docstring."""
    prefix = "location:"
    suffix = f":{GeographicKnowledgeAspect.EXISTENCE.value.lower()}"
    rows = (
        db.query(KnowledgeFact.fact_key)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character_id,
            KnowledgeFact.fact_key.like(f"{prefix}%{suffix}"),
        )
        .all()
    )
    ids = set()
    for (fact_key,) in rows:
        if not fact_key.startswith(prefix) or not fact_key.endswith(suffix):
            continue
        ids.add(fact_key[len(prefix):-len(suffix)])
    return ids


def _phase17_rumored_location_ids(db: Session, campaign_id: str, character_id: str) -> set[str]:
    """Locations the character has only ever heard a RUMORED EXISTENCE
    claim about (app.game.knowledge.rumors' ":rumor:" fact_key
    namespace) — distinct from _phase17_known_location_ids, which only
    ever matches the canonical (confirmed) fact_key. See module
    docstring."""
    prefix = "location:"
    marker = f":{GeographicKnowledgeAspect.EXISTENCE.value.lower()}:rumor:"
    rows = (
        db.query(KnowledgeFact.fact_key)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character_id,
            KnowledgeFact.fact_key.like(f"{prefix}%{marker}%"),
        )
        .all()
    )
    ids = set()
    for (fact_key,) in rows:
        if not fact_key.startswith(prefix) or marker not in fact_key:
            continue
        ids.add(fact_key[len(prefix):].split(marker, 1)[0])
    return ids


def _owned_map_contents_by_location(db: Session, character_id: str) -> dict[str, list[dict]]:
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
    by_location: dict[str, list[dict]] = {}
    for map_row in map_rows:
        by_location.setdefault(map_row.entity_id, []).append(map_content(map_row))
    return by_location


def _build_map_view_location_from_maps(
    location: Location,
    discovery_status: DiscoveryStatus,
    contents: list[dict],
) -> MapViewLocation:
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
        known_aspects=sorted(known_aspect_values),
    )


def _build_map_view_location(
    db: Session,
    campaign_id: str,
    character_id: str,
    location: Location,
    discovery_status: DiscoveryStatus,
    *,
    source: str = "discovery",
) -> MapViewLocation:
    precision = _best_known_precision(db, campaign_id, character_id, location, discovery_status)
    name_known = _knows_name_aspect(
        db, campaign_id, character_id, location.id
    ) or explicitly_knows_name(db, campaign_id, KnowerType.PLAYER, character_id, location.name)
    exact_position_known = precision == GeographicPrecision.PRECISE

    known_aspects = {
        aspect.value
        for aspect in known_geographic_aspects(
            db, campaign_id, KnowerType.PLAYER, character_id, "location", location.id
        )
    }
    # Appearing in the view at all always means EXISTENCE is known — true
    # whether that came from a Phase 17 grant or from ordinary physical
    # discovery/travel, which never writes an explicit EXISTENCE fact.
    known_aspects.add(GeographicKnowledgeAspect.EXISTENCE.value)
    if name_known:
        known_aspects.add(GeographicKnowledgeAspect.NAME.value)

    return MapViewLocation(
        id=location.id,
        region_id=location.region_id,
        subregion_id=location.subregion_id,
        parent_location_id=location.parent_location_id,
        type=location.type,
        name=location.name if name_known else None,
        precision=precision.value if precision is not None else None,
        x=location.x if exact_position_known else None,
        y=location.y if exact_position_known else None,
        discovery_status=discovery_status.value,
        source=source,
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


def get_map_view(
    db: Session,
    campaign_id: str,
    character_id: str,
    *,
    scope: str | None = None,
) -> MapViewData:
    data = known_map(db, campaign_id, character_id)

    locations: list[MapViewLocation] = []
    seen_location_ids: set[str] = set()
    for location in data["locations"]:
        discovery_status = DiscoveryStatus(data["location_discovery"][location.id])
        locations.append(_build_map_view_location(db, campaign_id, character_id, location, discovery_status))
        seen_location_ids.add(location.id)

    regions_by_id = {region.id: region for region in data["regions"]}

    phase17_only_ids = _phase17_known_location_ids(db, campaign_id, character_id) - seen_location_ids
    if phase17_only_ids:
        extra_locations = (
            db.query(Location)
            .join(Region, Region.id == Location.region_id)
            .filter(Location.id.in_(phase17_only_ids), Region.campaign_id == campaign_id)
            .order_by(Location.name)
            .all()
        )
        for location in extra_locations:
            # No CharacterLocationDiscovery row exists for this location —
            # RUMORED is the closest existing status to "aware it exists,
            # never physically encountered it".
            locations.append(
                _build_map_view_location(
                    db, campaign_id, character_id, location, DiscoveryStatus.RUMORED, source="knowledge"
                )
            )
            if location.region_id not in regions_by_id:
                region = db.get(Region, location.region_id)
                if region is not None:
                    regions_by_id[region.id] = region

    included_location_ids = {location.id for location in locations}
    map_contents_by_location = _owned_map_contents_by_location(db, character_id)
    map_only_ids = set(map_contents_by_location.keys()) - included_location_ids
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
                    location, DiscoveryStatus.RUMORED, map_contents_by_location[location.id]
                )
            )
            if location.region_id not in regions_by_id:
                region = db.get(Region, location.region_id)
                if region is not None:
                    regions_by_id[region.id] = region

    included_location_ids = {location.id for location in locations}
    rumored_only_ids = _phase17_rumored_location_ids(db, campaign_id, character_id) - included_location_ids
    if rumored_only_ids:
        rumored_locations = (
            db.query(Location)
            .join(Region, Region.id == Location.region_id)
            .filter(Location.id.in_(rumored_only_ids), Region.campaign_id == campaign_id)
            .order_by(Location.name)
            .all()
        )
        for location in rumored_locations:
            locations.append(
                _build_map_view_location(
                    db, campaign_id, character_id, location, DiscoveryStatus.RUMORED, source="rumor"
                )
            )
            if location.region_id not in regions_by_id:
                region = db.get(Region, location.region_id)
                if region is not None:
                    regions_by_id[region.id] = region

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

    visible_location_ids = {location.id for location in locations}
    routes = [
        MapViewRoute(
            from_location_id=connection.from_location_id,
            to_location_id=connection.to_location_id,
            direction=connection.direction,
            connection_type=connection.connection_type,
            distance=connection.distance,
            danger=connection.danger,
        )
        for connection in data["connections"]
        if connection.from_location_id in visible_location_ids
        and connection.to_location_id in visible_location_ids
    ]

    return MapViewData(
        campaign_id=campaign_id,
        character_id=character_id,
        scope=scope,
        regions=regions,
        locations=locations,
        routes=routes,
    )
