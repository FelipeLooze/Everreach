"""Authoritative bindings only; never bypass character discovery in a player view."""
from sqlalchemy.orm import Session

from app.db.models.location import Location, LocationConnection
from app.db.models.region import Region
from app.db.models.subregion import Subregion
from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_spatial import EntitySpatialCoverage, GenesisSphereSector, LocationSpatialAnchor
from .sphere_config import SphereConfig, parse_config
from .sphere_metric import distance_m
from .sphere_topology import CellKey, SurfacePoint, cell_at, cell_contains, nearby_cells


def sphere_world(db: Session, campaign_id: str) -> tuple[GenesisWorld, SphereConfig]:
    world = db.get(GenesisWorld, campaign_id)
    if world is None:
        raise ValueError("World must be explicitly initialized")
    config = parse_config(world.config)
    if not isinstance(config, SphereConfig):
        raise ValueError("Spatial bindings require a spherical world; legacy coordinates cannot be converted implicitly")
    return world, config


def _region(db: Session, campaign_id: str, region_id: str) -> Region:
    region = db.get(Region, region_id)
    if region is None or region.campaign_id != campaign_id:
        raise ValueError("Entity does not belong to this campaign")
    return region


def bind_location(db: Session, campaign_id: str, location_id: str, point: SurfacePoint) -> LocationSpatialAnchor:
    sphere_world(db, campaign_id)
    location = db.get(Location, location_id)
    if location is None:
        raise ValueError("Unknown location")
    _region(db, campaign_id, location.region_id)
    if not isinstance(point, SurfacePoint):
        raise ValueError("Expected a canonical SurfacePoint")
    existing = db.get(LocationSpatialAnchor, location_id)
    if existing is not None:
        if existing.campaign_id != campaign_id or existing.point != list(point.xyz):
            raise ValueError("A location's physical anchor cannot change implicitly")
        return existing
    anchor = LocationSpatialAnchor(campaign_id=campaign_id, location_id=location_id, point=list(point.xyz))
    db.add(anchor)
    db.flush()
    return anchor


def add_coverage(db: Session, campaign_id: str, cell: CellKey, *,
                 region_id: str | None = None, subregion_id: str | None = None) -> EntitySpatialCoverage:
    _, config = sphere_world(db, campaign_id)
    if not isinstance(cell, CellKey) or cell.level > config.sector_level:
        raise ValueError("Coverage cells must be at sector level or a coarser ancestor")
    if (region_id is None) == (subregion_id is None):
        raise ValueError("Coverage must have exactly one Region or Subregion owner")
    if region_id is not None:
        _region(db, campaign_id, region_id)
    else:
        subregion = db.get(Subregion, subregion_id)
        if subregion is None:
            raise ValueError("Unknown subregion")
        _region(db, campaign_id, subregion.region_id)
    address = dict(campaign_id=campaign_id, region_id=region_id, subregion_id=subregion_id,
                   face=cell.face, level=cell.level, x=cell.x, y=cell.y)
    existing = db.query(EntitySpatialCoverage).filter_by(**address).one_or_none()
    if existing is not None:
        return existing
    coverage = EntitySpatialCoverage(**address)
    db.add(coverage)
    db.flush()
    return coverage


def coverage_contains(coverage: EntitySpatialCoverage, point: SurfacePoint) -> bool:
    """Closed geometric cell: seam points can belong to coverage on either face."""
    return cell_contains(CellKey(coverage.face, coverage.level, coverage.x, coverage.y), point)


def location_preparation_plan(db: Session, campaign_id: str, location_id: str,
                              radius: int = 1) -> list[CellKey]:
    """Internal integration hook: bounded plan only, without revealing or generating terrain."""
    _, config = sphere_world(db, campaign_id)
    location = db.get(Location, location_id)
    if location is None:
        raise ValueError("Unknown location")
    _region(db, campaign_id, location.region_id)
    anchor = db.get(LocationSpatialAnchor, location_id)
    if anchor is None or anchor.campaign_id != campaign_id:
        raise ValueError("Location requires an explicit anchor in this world")
    return nearby_cells(cell_at(SurfacePoint(*anchor.point), config.sector_level), radius)


def prepare_location_sector(db: Session, campaign_id: str, location_id: str) -> GenesisSphereSector:
    """Materialize only the anchor's sector, for explicit campaign start/travel orchestration."""
    from .service import materialize_sector
    key = location_preparation_plan(db, campaign_id, location_id, radius=0)[0]
    return materialize_sector(db, campaign_id, key)


def connection_geographic_distance(db: Session, campaign_id: str, connection_id: str) -> float | None:
    """Great-circle lower bound only. Does not modify route length, duration or risk."""
    _, config = sphere_world(db, campaign_id)
    connection = db.get(LocationConnection, connection_id)
    if connection is None:
        raise ValueError("Unknown physical connection")
    anchors = []
    for location_id in (connection.from_location_id, connection.to_location_id):
        location = db.get(Location, location_id)
        _region(db, campaign_id, location.region_id)
        anchor = db.get(LocationSpatialAnchor, location_id)
        if anchor is not None and anchor.campaign_id != campaign_id:
            raise ValueError("Anchor belongs to another campaign")
        anchors.append(SurfacePoint(*anchor.point) if anchor is not None else None)
    if any(anchor is None for anchor in anchors):
        return None
    return distance_m(config, *anchors)
