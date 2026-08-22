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
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import Location
from app.db.models.region import Region
from app.game.knowledge.geography import (
    geographic_fact_key,
    geographic_knowledge_precision,
    known_geographic_aspects,
    precision_rank,
)
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
    type: str
    name: str | None
    precision: str | None
    x: int | None
    y: int | None
    discovery_status: str
    known_aspects: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MapViewRegion:
    id: str
    name: str | None
    discovery_status: str


@dataclass(frozen=True)
class MapViewData:
    """Deliberately the smallest extensible shape for 20A — a future
    subphase adds fields (routes, rumors, physical-map sources, player
    annotations, LOD/viewport scoping), not restructures this one.

    20B adds `regions` — grouping metadata the interactive frontend needs
    to render locations by region, gated by the same
    explicitly_knows_name convention the old /map route already used."""

    campaign_id: str
    character_id: str
    scope: str | None
    regions: list[MapViewRegion] = field(default_factory=list)
    locations: list[MapViewLocation] = field(default_factory=list)


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


def _build_map_view_location(
    db: Session,
    campaign_id: str,
    character_id: str,
    location: Location,
    discovery_status: DiscoveryStatus,
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
        type=location.type,
        name=location.name if name_known else None,
        precision=precision.value if precision is not None else None,
        x=location.x if exact_position_known else None,
        y=location.y if exact_position_known else None,
        discovery_status=discovery_status.value,
        known_aspects=sorted(known_aspects),
    )


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
                _build_map_view_location(db, campaign_id, character_id, location, DiscoveryStatus.RUMORED)
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

    return MapViewData(
        campaign_id=campaign_id,
        character_id=character_id,
        scope=scope,
        regions=regions,
        locations=locations,
    )
