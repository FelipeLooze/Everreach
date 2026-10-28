"""TP1: bounded physical preparation feeding the existing Location graph.

Only newly started AP1 campaigns opt in. Cells address sites, not a second
navigation graph. Connections remain the sole authority for player travel.
"""
from math import atan2, ceil, degrees, hypot, log2, sqrt
from time import perf_counter

from app.db.models.campaign import Campaign
from app.db.models.location import Location, LocationConnection, LocationFeature
from app.db.models.region import Region
from app.db.models.subregion import Subregion
from app.db.models.world_spatial import LocationSpatialAnchor
from .sphere_topology import CellKey, SurfacePoint, cell_at, cell_center, neighbor, DIRECTIONS
from .sphere_metric import distance_m
from .spatial import sphere_world, bind_location, add_coverage, prepare_location_sector
from .terrain.field import checksum
from .terrain.service import query_altitude
from .hydrology.service import get_hydrology_plan
from .formation_plan import cell_index

VERSION = 'territory_tp1'
METRES_PER_COST_UNIT = 1000  # TP1 only; legacy distance retains its old meaning.
MAX_ROUTE_SAMPLES = 33


def _id(cid, kind, value):
    return 'tp1_' + kind + '_' + checksum([VERSION, cid, kind, value])[:24]


def _unit(point):
    n = sqrt(sum(v*v for v in point.xyz))
    return tuple(v/n for v in point.xyz)


def _point(db, cid, location):
    anchor = db.get(LocationSpatialAnchor, location.id)
    region = db.get(Region, location.region_id)
    if anchor is None or anchor.campaign_id != cid or region is None or region.campaign_id != cid:
        raise ValueError('TP1 requires a persistent anchor in this campaign')
    point = SurfacePoint(*anchor.point)
    if location.genesis_site is None or list(point.xyz) != location.genesis_site['point']:
        raise ValueError('TP1 site/anchor mismatch; no automatic relocation')
    cell = CellKey(**location.genesis_site['cell'])
    if cell_at(point,cell.level) != cell:
        raise ValueError('TP1 site/cell mismatch')
    return point


def _contract(db, cid):
    campaign = db.get(Campaign, cid)
    if campaign is None:
        raise ValueError('Unknown TP1 campaign')
    descriptor = (campaign.playable_state or {}).get('territory')
    world, config = sphere_world(db, cid)
    if not descriptor or descriptor['version'] != VERSION or descriptor['world_config'] != world.config:
        raise ValueError('TP1 requires explicit persisted opt-in and unchanged geography')
    return descriptor, config


def _coverage(db, cid, key, root_region=None):
    _, config = sphere_world(db, cid)
    sector = key.parent(min(key.level, config.sector_level))
    macro = sector.parent(max(0, sector.level-3))
    rid = _id(cid, 'region', vars(macro))
    region = root_region or db.get(Region, rid)
    if region is None:
        region = Region(id=rid, campaign_id=cid, name='Território '+rid[-6:],
                        description='Área geográfica de exploração; não representa um continente ou domínio político.')
        db.add(region); db.flush()
    add_coverage(db, cid, macro, region_id=region.id)
    sid = _id(cid, 'subregion', vars(sector))
    sub = db.get(Subregion, sid)
    if sub is None:
        sub = Subregion(id=sid, region_id=region.id, name='Setor '+sid[-6:],
                        biome='GENESIS_POINT_MOSAIC', danger_level='UNDETERMINED', population_density='UNDETERMINED')
        db.add(sub); db.flush()
    add_coverage(db, cid, sector, subregion_id=sub.id)
    return region.id, sub.id


def initialize_territory(db, campaign, location):
    """Called only inside first-start transaction, never on an established save."""
    world, config = sphere_world(db, campaign.id)
    level = min(24, max(config.sector_level, ceil(log2(2*config.radius_m/1000))))
    point = SurfacePoint(*db.get(LocationSpatialAnchor, location.id).point)
    key = cell_at(point, level)
    # Stable physical grouping, even though AP1's root Region already exists.
    location.region_id, location.subregion_id = _coverage(db, campaign.id, key, db.get(Region, location.region_id))
    descriptor = {'version': VERSION, 'level': level, 'world_config': world.config,
                  'root_cell': vars(key), 'root_point': list(point.xyz),
                  'root_region_cell': vars(key.parent(max(0, config.sector_level-3))),
                  'root_region_id': location.region_id, 'root_location_id': location.id}
    campaign.playable_state = {**campaign.playable_state, 'territory': descriptor}
    location.genesis_site = {'version': VERSION, 'cell': vars(key), 'point': list(point.xyz), 'prepared': False}
    db.flush()
    prepare_site(db, location)


def _site(db, cid, key, descriptor):
    if vars(key) == descriptor['root_cell']:
        return db.get(Location, descriptor['root_location_id'])
    lid = _id(cid, 'location', vars(key))
    existing = db.get(Location, lid)
    if existing is not None:
        _point(db, cid, existing)
        return existing
    root_macro = CellKey(**descriptor['root_region_cell'])
    root = db.get(Region, descriptor['root_region_id']) if key.parent(root_macro.level) == root_macro else None
    rid, sid = _coverage(db, cid, key, root)
    point = cell_center(key)
    # Existing map's schematic coordinates, in 100 m tangent projection units.
    # They are never the physical position, and retain its discovery filtering.
    origin = _unit(SurfacePoint(*descriptor['root_point']))
    east = (-origin[1], origin[0], 0)
    length = hypot(*east[:2])
    east = tuple(v/length for v in east) if length else (0, 1, 0)
    north = (origin[1]*east[2]-origin[2]*east[1], origin[2]*east[0]-origin[0]*east[2], origin[0]*east[1]-origin[1]*east[0])
    ray = _unit(point)
    radius = descriptor['world_config']['radius_m']
    location = Location(id=lid, region_id=rid, subregion_id=sid, name='Área '+checksum([vars(key)])[:6],
        type='genesis_field', materialization_tier=2,
        x=round(radius*sum(a*b for a,b in zip(ray,east))/100),
        y=round(radius*sum(a*b for a,b in zip(ray,north))/100),
        genesis_site={'version': VERSION, 'cell': vars(key), 'point': list(point.xyz), 'prepared': False})
    db.add(location); db.flush(); bind_location(db, cid, lid, point)
    return location


def route_evidence(config, a, b, sample):
    """Symmetric, bounded great-circle corridor. T1 has no current water overlay.

    Ocean datum and slopes are conservative foot-travel barriers, not invented
    rivers or lakes. Sub-sample obstacles and detours are explicitly unresolved.
    """
    a, b = sorted((a, b), key=lambda p: p.xyz)
    metres = distance_m(config, a, b)
    steps = max(2, ceil(metres/100))
    if steps+1 > MAX_ROUTE_SAMPLES:
        return {'blocked': 'corredor excede a resolução de travessia TP1', 'metres': metres, 'samples': []}
    u, v = _unit(a), _unit(b)
    points = [a] + [SurfacePoint(*(round(((1-i/steps)*x+(i/steps)*y)*10**15) for x,y in zip(u,v))) for i in range(1,steps)] + [b]
    sampled = [sample(p) for p in points]
    heights = [s['height_mm']/1000 for s in sampled]
    segments = [distance_m(config, p,q) for p,q in zip(points,points[1:])]
    grades = [abs(y-x)/max(d, 0.001) for x,y,d in zip(heights,heights[1:],segments)]
    ocean = [s.get('reference_ocean_H1', False) for s in sampled]
    blocked = ('superfície oceânica de referência' if any(h <= config.sea_level_m and marine for h,marine in zip(heights,ocean)) else
               'encosta acima do limite pedestre de 45 graus' if max(grades)>1 else None)
    length = sum(hypot(d, y-x) for x,y,d in zip(heights,heights[1:],segments))
    return {'blocked': blocked, 'metres': length, 'surface_metres': metres,
            'max_grade': max(grades), 'modifier': 1+2*sum(grades)/len(grades),
            'samples': [{'point': list(p.xyz), 'height_m': h, 'reference_ocean_H1': marine} for p,h,marine in zip(points,heights,ocean)]}


def _direction(a, b):
    u, v = _unit(a), _unit(b)
    lon = atan2(u[1],u[0]); lat = atan2(u[2],hypot(u[0],u[1]))
    from math import sin, cos
    east = (-sin(lon), cos(lon), 0)
    north = (-sin(lat)*cos(lon), -sin(lat)*sin(lon), cos(lat))
    angle = degrees(atan2(sum(x*y for x,y in zip(v,east)),sum(x*y for x,y in zip(v,north)))) % 360
    return ('norte','nordeste','leste','sudeste','sul','sudoeste','oeste','noroeste')[int((angle+22.5)//45)%8]


def prepare_site(db, location):
    """One site plus four anchored stubs. Caller owns transaction; no recursion."""
    if location.genesis_site is None:
        return location
    cid = db.get(Region, location.region_id).campaign_id
    descriptor, config = _contract(db, cid)
    point = _point(db, cid, location)
    if location.genesis_site['version'] != VERSION:
        raise ValueError('Unsupported site version')
    if location.genesis_site['prepared']:
        return location
    started = perf_counter()
    from .environment.service import materialize_environment_point
    from .vegetation.service import materialize_community
    prepare_location_sector(db, cid, location.id)
    environment = materialize_environment_point(db, cid, point)
    from app.db.models.campaign import Campaign
    campaign = db.get(Campaign, cid)
    wgs2_v3 = campaign.world_profile == "world_genesis_ap1_tp1_wgs2_v3"
    from .local_formations import materialize_for_site
    if wgs2_v3:
        # Resolve bounded WGS2 origins before sampling this site's plant community.
        materialize_for_site(db, campaign, location)
    community = materialize_community(db, cid, point)
    height = query_altitude(db, cid, point)['height_mm']/1000
    location.description = f'Terreno a aproximadamente {round(height)} m do nível de referência. A vegetação próxima pode ser observada e examinada.'
    db.add(LocationFeature(id=_id(cid,'feature',location.id), location_id=location.id,
                          name='Relevo local', description=f'Altitude aproximada: {round(height)} m.'))
    key = CellKey(**location.genesis_site['cell'])
    hydrology = get_hydrology_plan(db, cid)
    def sample_route(p):
        return {**query_altitude(db,cid,p),
                'reference_ocean_H1': hydrology.drainage.marine[cell_index(cell_at(p,hydrology.config.level))]}
    for direction in DIRECTIONS:
        destination = _site(db, cid, neighbor(key,direction), descriptor)
        target = _point(db, cid, destination)
        if db.get(LocationConnection, _id(cid,'route',[location.id,destination.id])) is not None:
            continue
        evidence = route_evidence(config, point, target, sample_route)
        for source, end, a, b in ((location,destination,point,target),(destination,location,target,point)):
            contract = {'version': VERSION, 'metres_per_cost_unit': METRES_PER_COST_UNIT,
                        'hydrology_signature': hydrology.signature,
                        'from_point': list(a.xyz), 'to_point': list(b.xyz), **evidence}
            contract['checksum'] = checksum(contract)
            db.add(LocationConnection(id=_id(cid,'route',[source.id,end.id]),
                from_location_id=source.id, to_location_id=end.id, direction=_direction(a,b),
                distance=evidence['metres']/METRES_PER_COST_UNIT, danger=0,
                travel_time_modifier=evidence.get('modifier',1), active=evidence['blocked'] is None,
                spatial_contract=contract))
        if evidence['blocked']:
            db.add(LocationFeature(id=_id(cid,'barrier',[location.id,destination.id]), location_id=location.id,
                name='Travessia indisponível', description=f"Rumo a {_direction(point,target)}: {evidence['blocked']}.", visible=True))
    location.materialization_tier = 1
    location.genesis_site = {**location.genesis_site, 'prepared': True,
        'environment_checksum': environment.baseline_checksum,
        'community_id': community.community_id, 'preparation_seconds': perf_counter()-started}
    db.flush()
    if not wgs2_v3:
        materialize_for_site(db, campaign, location)
    return location


def validate_travel(db, cid, connection):
    """Do not let an arbitrary graph edge bypass the physical TP1 contract."""
    source = db.get(Location, connection.from_location_id)
    target = db.get(Location, connection.to_location_id)
    if not source.genesis_site and not target.genesis_site:
        return
    _, config = _contract(db, cid)
    a, b = _point(db, cid, source), _point(db, cid, target)
    c = connection.spatial_contract
    if c and c.get('version') in ('WGS1_LOCAL_ACCESS', 'WGS2_LOCAL_ACCESS', 'WGS2_COVERAGE_ACCESS', 'WGS2_COVERAGE_ACCESS_V2'):
        from app.db.models.world_natural_formations import GenesisNaturalFormation, GenesisFormationCoverageCell
        from .local_formations import VERSION as WGS1_VERSION, VERSION_V2 as WGS1_VERSION_V2, VERSION_WGS2, VERSION_WGS2_V2
        instance = db.get(GenesisNaturalFormation, c.get('formation_id'))
        anchor_a = db.get(LocationSpatialAnchor, source.id)
        anchor_b = db.get(LocationSpatialAnchor, target.id)
        valid_location_ids = {instance.location_id} if instance else set()
        interior = db.query(Location).filter(Location.parent_location_id.in_(valid_location_ids)).all() if valid_location_ids else []
        valid_location_ids.update(row.id for row in interior)
        if c.get('version') in ('WGS2_COVERAGE_ACCESS', 'WGS2_COVERAGE_ACCESS_V2') and instance is not None:
            coverage = db.query(GenesisFormationCoverageCell).filter_by(
                id=c.get('coverage_id'), formation_id=instance.id,
                access_location_id=source.id if source.type == 'genesis_formation_access' else target.id).one_or_none()
            rows = db.query(GenesisFormationCoverageCell).filter_by(
                campaign_id=cid, formation_id=instance.id,
                contract_version='WGS2_COVERAGE_V2').all()
            from .wgs2_coverage import persisted_coverage_valid
            span = instance.data.get('dimensions', {}).get('horizontal_span_m')
            coverage_valid = coverage is not None and type(span) is int and persisted_coverage_valid(rows, instance.stable_key, span)
            policy_valid = (c.get('version') == 'WGS2_COVERAGE_ACCESS'
                            or c.get('selection_policy') == 'wgs2-overlap-priority-stable-key-r2')
            if coverage_valid and policy_valid and c.get('coverage_checksum') == coverage.contract_checksum:
                valid_location_ids.add(coverage.access_location_id)
        expected = {k:v for k,v in c.items() if k!='checksum'}
        allowed_versions = (WGS1_VERSION, WGS1_VERSION_V2, VERSION_WGS2, VERSION_WGS2_V2) if c.get('version') in ('WGS2_LOCAL_ACCESS', 'WGS2_COVERAGE_ACCESS', 'WGS2_COVERAGE_ACCESS_V2') else (WGS1_VERSION, WGS1_VERSION_V2)
        if (not instance or instance.generator_version not in allowed_versions
            or source.id not in valid_location_ids and target.id not in valid_location_ids
            or not anchor_a or not anchor_b
            or anchor_a.point != list(a.xyz) or anchor_b.point != list(b.xyz)
            or c.get('from_point') != list(a.xyz) or c.get('to_point') != list(b.xyz)
            or c.get('checksum') != checksum(expected) or not connection.active
            or connection.distance != c.get('distance_m', 0)/METRES_PER_COST_UNIT
            or connection.travel_time_modifier != 1
            or (a.xyz != b.xyz and abs(distance_m(config,a,b)-c.get('distance_m',0)) > 0.5)
            or (a.xyz == b.xyz and not (source.type == 'genesis_formation_interior' or target.type == 'genesis_formation_interior'))):
            raise ValueError('WGS1 local access contract missing or changed')
        return
    if not c or c.get('version') != VERSION or c.get('checksum') != checksum({k:v for k,v in c.items() if k!='checksum'}):
        raise ValueError('TP1 route contract missing or changed')
    if c['from_point'] != list(a.xyz) or c['to_point'] != list(b.xyz) or c['blocked'] or not connection.active:
        raise ValueError('TP1 route anchors or traversability mismatch')
    if (c['metres_per_cost_unit'] != METRES_PER_COST_UNIT
            or connection.distance != c['metres']/METRES_PER_COST_UNIT
            or connection.travel_time_modifier != c['modifier']):
        raise ValueError('TP1 route cost mismatch')
    # Current overlay guard: changed T1 cannot silently reuse an old route.
    hydrology = get_hydrology_plan(db,cid)
    if hydrology.signature != c['hydrology_signature']:
        raise ValueError('TP1 hydrology reference changed')
    for sample in c['samples']:
        if query_altitude(db,cid,SurfacePoint(*sample['point']))['height_mm']/1000 != sample['height_m']:
            raise ValueError('TP1 terrain changed; route requires explicit reassessment')
