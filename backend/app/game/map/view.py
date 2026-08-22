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
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.location import Location
from app.game.knowledge.geography import geographic_fact_key, geographic_knowledge_precision, precision_rank
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


def get_map_view(
    db: Session,
    campaign_id: str,
    character_id: str,
    *,
    scope: str | None = None,
) -> MapViewData:
    data = known_map(db, campaign_id, character_id)

    locations: list[MapViewLocation] = []
    for location in data["locations"]:
        discovery_status = DiscoveryStatus(data["location_discovery"][location.id])
        precision = _best_known_precision(db, campaign_id, character_id, location, discovery_status)
        name_known = _knows_name_aspect(
            db, campaign_id, character_id, location.id
        ) or explicitly_knows_name(db, campaign_id, KnowerType.PLAYER, character_id, location.name)
        exact_position_known = precision == GeographicPrecision.PRECISE

        locations.append(
            MapViewLocation(
                id=location.id,
                region_id=location.region_id,
                type=location.type,
                name=location.name if name_known else None,
                precision=precision.value if precision is not None else None,
                x=location.x if exact_position_known else None,
                y=location.y if exact_position_known else None,
                discovery_status=discovery_status.value,
            )
        )

    regions = []
    for region in data["regions"]:
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

    return MapViewData(
        campaign_id=campaign_id,
        character_id=character_id,
        scope=scope,
        regions=regions,
        locations=locations,
    )
