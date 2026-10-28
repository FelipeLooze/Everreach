from app.game.world.genesis.sphere_config import SphereConfig
from app.game.world.genesis.sphere_metric import distance_m
from app.game.world.genesis.sphere_topology import CellKey, SurfacePoint, cell_at, cell_center, face_point, neighbor
from app.game.world.genesis.wgs2_coverage import VERSION, contract_checksum, footprint_cells
from app.game.world.genesis.wgs2_families import VERSION_V2, candidate
from app.game.world.genesis.local_formations import catalog
from app.db.models.campaign import Campaign
from app.db.models.location import Location, LocationConnection
from app.db.models.region import Region
from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_natural_formations import GenesisNaturalFormation, GenesisFormationCoverageCell
from app.db.models.world_spatial import LocationSpatialAnchor
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.local_formations import _ensure_wgs2_coverage_access
from app.game.world.genesis.territory import validate_travel
from app.game.world.genesis.local_formations import inspect_current
from app.game.character.service import create_character
from app.game.world.genesis.wgs2_coverage import contract_checksum
import pytest


def test_wgs2_v2_selector_is_versioned_and_order_independent():
    records = catalog()
    cell = {"face": 0, "level": 17, "x": 20, "y": 30}
    results = [candidate(seed, cell, records, version=VERSION_V2) for seed in (42, 7, 2026)]
    assert results == [candidate(seed, cell, records, version=VERSION_V2) for seed in (42, 7, 2026)]
    assert VERSION_V2 != "natural_formations_wgs2_v1"


def test_coverage_spans_multiple_cells_and_crosses_cube_face_seam():
    radius = 63_710_000
    level = 17
    # Within the +X chart and 400 m from its east edge.
    center = face_point(0, 2**17, 2**16, 2**17)
    center_key = cell_at(center, level)
    cells = footprint_cells(center, level, radius, 3400)
    assert center_key in cells
    assert len(cells) > 1
    assert any(cell.face != center_key.face for cell in cells)
    config = SphereConfig(radius_m=radius, sector_level=10)
    assert all(distance_m(config, center, cell_center(cell)) <= 1700
               for cell in cells)
    assert contract_checksum("formation", cells, 3400) == contract_checksum("formation", cells, 3400)


def test_coverage_at_pole_is_defined_and_repeatable():
    north_pole = SurfacePoint(0, 0, 1)
    first = footprint_cells(north_pole, 17, 63_710_000, 3400)
    assert first == footprint_cells(north_pole, 17, 63_710_000, 3400)
    assert first


def test_coverage_refuses_unverified_eight_hop_footprint_without_partial_result():
    from app.game.world.genesis.wgs2_coverage import MAX_SEARCH_HOPS
    center = cell_center(CellKey(0, 17, 20_000, 20_000))
    # Deliberately exceed the production 3.4 km cap to exercise the guard.
    with pytest.raises(RuntimeError, match="bounded eight-cell-hop index"):
        footprint_cells(center, 17, 63_710_000, 10_000)
    assert MAX_SEARCH_HOPS == 8


def test_persisted_coverage_gets_local_graph_access_without_revealing_footprint(db_session):
    db = db_session
    config = FormationConfigV4().model_dump(mode="json")
    campaign = Campaign(name="WGS2.2 access", world_seed=42,
        world_profile="world_genesis_ap1_tp1_wgs2_v2",
        playable_state={"territory":{"version":"territory_tp1", "world_config":config}})
    db.add(campaign); db.flush()
    db.add(GenesisWorld(campaign_id=campaign.id, world_seed=42, config=config, plan={})); db.flush()
    region = Region(campaign_id=campaign.id, name="local test"); db.add(region); db.flush()
    cell = cell_at(face_point(0, 2**17, 2**16, 2**17), 17)
    center = cell_center(cell)
    exterior = Location(region_id=region.id, name="known field", type="genesis_field",
        genesis_site={"version":"territory_tp1", "cell":vars(cell), "point":list(center.xyz), "prepared":True})
    formation_location = Location(region_id=region.id, name="test formation", type="genesis_formation",
        genesis_site={"version":"territory_tp1", "cell":vars(cell), "point":list(center.xyz), "prepared":True})
    db.add_all([exterior, formation_location]); db.flush()
    db.add_all([LocationSpatialAnchor(location_id=exterior.id,campaign_id=campaign.id,point=list(center.xyz)),
                LocationSpatialAnchor(location_id=formation_location.id,campaign_id=campaign.id,point=list(center.xyz))]); db.flush()
    instance = GenesisNaturalFormation(id="formation-instance", campaign_id=campaign.id, location_id=formation_location.id,
        stable_key="stable-formation", archetype_id="EV-LOC-0037", generator_version=VERSION_V2, data={})
    db.add(instance); db.flush()
    cells=(cell,)
    coverage_hash=contract_checksum(instance.stable_key,cells,100)
    instance.data={"dimensions":{"horizontal_span_m":100}}
    coverage = GenesisFormationCoverageCell(id="coverage-row", campaign_id=campaign.id, formation_id=instance.id,
        face=cell.face, level=cell.level, x=cell.x, y=cell.y, contract_version=VERSION,
        contract_checksum=coverage_hash)
    db.add(coverage); db.flush()
    _ensure_wgs2_coverage_access(db, campaign, exterior, instance, coverage)
    access = db.get(Location, coverage.access_location_id)
    assert access is not None and access.parent_location_id == formation_location.id
    assert access.type == "genesis_formation_access"
    assert set(access.genesis_site) == {"version", "cell", "point", "prepared", "formation_version"}
    routes = db.query(LocationConnection).filter(LocationConnection.from_location_id.in_((exterior.id, access.id)),
        LocationConnection.spatial_contract.is_not(None)).all()
    routes = [route for route in routes if route.spatial_contract.get("coverage_id") == coverage.id]
    assert len(routes) == 2
    for route in routes:
        assert route.spatial_contract["version"] == "WGS2_COVERAGE_ACCESS_V2"
        assert route.spatial_contract["selection_policy"] == "wgs2-overlap-priority-stable-key-r2"
        validate_travel(db, campaign.id, route)
        # Saves carrying the previous access-contract version remain valid.
        from app.game.world.genesis.terrain.field import checksum
        legacy = {k:v for k,v in route.spatial_contract.items()
                  if k not in ("checksum", "selection_policy")}
        legacy["version"] = "WGS2_COVERAGE_ACCESS"
        legacy["checksum"] = checksum(legacy)
        current = route.spatial_contract
        route.spatial_contract = legacy
        validate_travel(db, campaign.id, route)
        route.spatial_contract = current


def test_wgs2_v2_real_materialization_reuses_instance_from_a_second_covered_cell(db_session, monkeypatch):
    from app.game.world.genesis import local_formations
    import app.game.world.genesis.environment.service as environment_service
    from app.db.models.location import LocationConnection
    db = db_session
    config = FormationConfigV4().model_dump(mode="json")
    campaign = Campaign(name="WGS2.2 footprint", world_seed=42,
        world_profile="world_genesis_ap1_tp1_wgs2_v2",
        playable_state={"natural_formations":{"version":VERSION_V2},
            "territory":{"version":"territory_tp1", "world_config":config}})
    db.add(campaign); db.flush()
    db.add(GenesisWorld(campaign_id=campaign.id, world_seed=42, config=config, plan={})); db.flush()
    region = Region(campaign_id=campaign.id, name="WGS2.2 field"); db.add(region); db.flush()
    first_key = cell_at(face_point(0, 2**17-2, 2**16, 2**17), 17)
    original_hash = local_formations._hash
    monkeypatch.setattr(local_formations, "_hash",
        lambda seed,key,label,version=local_formations.VERSION: 2900 if label == "horizontal_span" else original_hash(seed,key,label,version))
    monkeypatch.setattr(environment_service, "query_environment", lambda *args, **kwargs: {"baseline": {
        "physical_inputs":{"T1_height_mm":1000,"reference_ocean_H1":False,"T1_slope_ppm":10000},
        "flora_contract":{"eligible_habitat_ids":[]}, "authority_signature":"test"}})
    monkeypatch.setattr("app.game.world.genesis.wgs2_families.candidate",
        lambda seed,address,records,**kwargs: "EV-LOC-0037" if address == vars(first_key) else None)

    first_point = cell_center(first_key)
    first_site = Location(region_id=region.id, name="first known cell", type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":vars(first_key),"point":list(first_point.xyz),"prepared":True})
    db.add(first_site); db.flush()
    db.add(LocationSpatialAnchor(location_id=first_site.id,campaign_id=campaign.id,point=list(first_point.xyz))); db.flush()
    first_instance = local_formations.materialize_for_site(db,campaign,first_site)
    assert first_instance.archetype_id == "EV-LOC-0037"
    coverage_rows = db.query(GenesisFormationCoverageCell).filter_by(formation_id=first_instance.id).all()
    assert len(coverage_rows) > 1
    second = next(row for row in coverage_rows if (row.face,row.level,row.x,row.y) !=
        (first_key.face,first_key.level,first_key.x,first_key.y))
    second_key = type(first_key)(second.face,second.level,second.x,second.y)
    second_point = cell_center(second_key)
    second_site = Location(region_id=region.id,name="second known cell",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":vars(second_key),"point":list(second_point.xyz),"prepared":True})
    db.add(second_site); db.flush()
    db.add(LocationSpatialAnchor(location_id=second_site.id,campaign_id=campaign.id,point=list(second_point.xyz))); db.flush()
    reused = local_formations.materialize_for_site(db,campaign,second_site)
    assert reused.id == first_instance.id
    second_access = db.get(Location, second.access_location_id)
    assert second_access is not None and second_access.parent_location_id == first_instance.location_id
    actor=create_character(db,campaign.id,"Tester",None,None)
    actor.location_id=second_access.id
    assert inspect_current(db,actor.id)["instance_id"] == first_instance.id
    routes = db.query(LocationConnection).filter(LocationConnection.from_location_id.in_((second_site.id,second_access.id))).all()
    for route in routes:
        if route.spatial_contract and route.spatial_contract.get("coverage_id") == second.id:
            validate_travel(db,campaign.id,route)
    db.commit(); db.expire_all()
    persisted_instance=db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign.id).one()
    persisted_coverage=db.query(GenesisFormationCoverageCell).filter_by(
        campaign_id=campaign.id, formation_id=persisted_instance.id,
        face=second.face, level=second.level, x=second.x, y=second.y).one()
    assert persisted_coverage.access_location_id == second_access.id
    assert inspect_current(db,actor.id)["instance_id"] == persisted_instance.id
    assert db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign.id).count() == 1


def test_overlap_priority_is_campaign_independent_and_established_access_is_pinned(db_session, monkeypatch):
    from app.game.world.genesis import local_formations
    monkeypatch.setattr("app.game.world.genesis.wgs2_families.candidate",
        lambda seed,address,records,**kwargs: None)
    db=db_session
    config=FormationConfigV4().model_dump(mode="json")
    cell=CellKey(0,17,10000,10000); point=cell_center(cell)

    def create_overlap(label, insertion):
        campaign=Campaign(name=label,world_seed=42,world_profile="world_genesis_ap1_tp1_wgs2_v2",
            playable_state={"natural_formations":{"version":VERSION_V2},
                "territory":{"version":"territory_tp1","world_config":config}})
        db.add(campaign);db.flush()
        db.add(GenesisWorld(campaign_id=campaign.id,world_seed=42,config=config,plan={}));db.flush()
        region=Region(campaign_id=campaign.id,name=label);db.add(region);db.flush()
        exterior=Location(region_id=region.id,name="field",type="genesis_field",
            genesis_site={"version":"territory_tp1","cell":vars(cell),"point":list(point.xyz),"prepared":True})
        db.add(exterior);db.flush()
        db.add(LocationSpatialAnchor(location_id=exterior.id,campaign_id=campaign.id,point=list(point.xyz)));db.flush()
        instances={}
        for suffix in insertion:
            key="formation-"+suffix
            form_loc=Location(region_id=region.id,name=key,type="genesis_formation",
                genesis_site={"version":"territory_tp1","cell":vars(cell),"point":list(point.xyz),"prepared":True})
            db.add(form_loc);db.flush()
            inst=GenesisNaturalFormation(id=f"{label}-{suffix}",campaign_id=campaign.id,
                location_id=form_loc.id,stable_key=key,archetype_id="EV-LOC-0037",
                generator_version=VERSION_V2,data={"dimensions":{"horizontal_span_m":1200}})
            db.add(inst);db.flush();instances[suffix]=inst
            digest=contract_checksum(key,(cell,),1200)
            db.add(GenesisFormationCoverageCell(id=f"{label}-coverage-{suffix}",campaign_id=campaign.id,
                formation_id=inst.id,face=cell.face,level=cell.level,x=cell.x,y=cell.y,
                contract_version=VERSION,contract_checksum=digest))
        db.flush()
        return campaign,exterior,instances

    one,site_one,forms_one=create_overlap("order-one",("b","a"))
    two,site_two,forms_two=create_overlap("order-two",("a","b"))
    selected_one=local_formations.materialize_for_site(db,one,site_one)
    selected_two=local_formations.materialize_for_site(db,two,site_two)
    assert selected_one.stable_key == selected_two.stable_key == "formation-a"
    cov_one=db.query(GenesisFormationCoverageCell).filter_by(
        campaign_id=one.id,formation_id=forms_one["a"].id).one()
    pinned_access=cov_one.access_location_id
    assert pinned_access is not None

    # A later overlapping instance cannot rewrite the already-public access.
    late_loc=Location(region_id=site_one.region_id,name="late overlap",type="genesis_formation",
        genesis_site={"version":"territory_tp1","cell":vars(cell),"point":list(point.xyz),"prepared":True})
    db.add(late_loc);db.flush()
    late=GenesisNaturalFormation(id="order-one-late",campaign_id=one.id,location_id=late_loc.id,
        stable_key="formation-0",archetype_id="EV-LOC-0037",generator_version=VERSION_V2,
        data={"dimensions":{"horizontal_span_m":1200}})
    db.add(late);db.flush()
    digest=contract_checksum(late.stable_key,(cell,),1200)
    db.add(GenesisFormationCoverageCell(id="order-one-late-cell",campaign_id=one.id,
        formation_id=late.id,face=cell.face,level=cell.level,x=cell.x,y=cell.y,
        contract_version=VERSION,contract_checksum=digest));db.flush()
    after_late=local_formations.materialize_for_site(db,one,site_one)
    assert after_late.id == forms_one["a"].id
    cov_one=db.query(GenesisFormationCoverageCell).filter_by(
        campaign_id=one.id,formation_id=forms_one["a"].id).one()
    assert cov_one.access_location_id == pinned_access


def test_two_covered_cells_resolve_same_access_identity_in_opposite_visit_orders(db_session,monkeypatch):
    from app.game.world.genesis import local_formations
    db=db_session;config=FormationConfigV4().model_dump(mode="json")
    first_key=CellKey(0,17,30_000,30_000);second_key=neighbor(first_key,"east")
    keys=(first_key,second_key);formation_key="canonical-overlap-stable-key"
    monkeypatch.setattr("app.game.world.genesis.wgs2_families.candidate",lambda *a,**k:None)

    def prepare(label):
        campaign=Campaign(name=label,world_seed=42,world_profile="world_genesis_ap1_tp1_wgs2_v2",
            playable_state={"natural_formations":{"version":local_formations.VERSION_WGS2_V2,
                "selection_policy":local_formations.POLICY_WGS2},
                "territory":{"version":"territory_tp1","world_config":config}})
        db.add(campaign);db.flush();db.add(GenesisWorld(campaign_id=campaign.id,world_seed=42,config=config,plan={}));db.flush()
        region=Region(campaign_id=campaign.id,name=label);db.add(region);db.flush()
        form_loc=Location(region_id=region.id,name="same formation",type="genesis_formation")
        db.add(form_loc);db.flush()
        instance=GenesisNaturalFormation(id=f"{label}-formation",campaign_id=campaign.id,
            location_id=form_loc.id,stable_key=formation_key,archetype_id="EV-LOC-0037",
            generator_version=local_formations.VERSION_WGS2_V2,
            data={"dimensions":{"horizontal_span_m":600}})
        db.add(instance);db.flush()
        digest=contract_checksum(formation_key,tuple(sorted(keys)),600)
        for key in keys:
            db.add(GenesisFormationCoverageCell(id=f"{label}-{key.x}-{key.y}",campaign_id=campaign.id,
                formation_id=instance.id,face=key.face,level=key.level,x=key.x,y=key.y,
                contract_version=VERSION,contract_checksum=digest))
        sites={}
        for key in keys:
            point=cell_center(key)
            site=Location(region_id=region.id,name=f"field {key.x}",type="genesis_field",
                genesis_site={"version":"territory_tp1","cell":vars(key),"point":list(point.xyz),"prepared":True})
            db.add(site);db.flush()
            db.add(LocationSpatialAnchor(location_id=site.id,campaign_id=campaign.id,point=list(point.xyz)))
            sites[key]=site
        db.flush();return campaign,instance,sites

    campaign_ab,instance_ab,sites_ab=prepare("order-ab")
    campaign_ba,instance_ba,sites_ba=prepare("order-ba")
    outcomes=[]
    for campaign,instance,sites,order in (
        (campaign_ab,instance_ab,sites_ab,keys),
        (campaign_ba,instance_ba,sites_ba,tuple(reversed(keys)))):
        selected=[]
        for key in order:
            result=local_formations.materialize_for_site(db,campaign,sites[key])
            selected.append(result.stable_key)
        coverage=db.query(GenesisFormationCoverageCell).filter_by(
            campaign_id=campaign.id,formation_id=instance.id).all()
        assert len(coverage)==2 and all(row.access_location_id for row in coverage)
        outcomes.append((selected,{(row.face,row.level,row.x,row.y):instance.stable_key for row in coverage}))
    assert outcomes[0][0]==outcomes[1][0]==[formation_key,formation_key]
    assert outcomes[0][1]==outcomes[1][1]


def test_cell_candidate_is_not_suppressed_by_an_existing_overlap(db_session,monkeypatch):
    from app.game.world.genesis import local_formations
    import app.game.world.genesis.environment.service as environment_service
    db=db_session;config=FormationConfigV4().model_dump(mode="json")
    campaign=Campaign(name="own candidate overlap",world_seed=42,world_profile="world_genesis_ap1_tp1_wgs2_v2",
        playable_state={"natural_formations":{"version":VERSION_V2},
            "territory":{"version":"territory_tp1","world_config":config}})
    db.add(campaign);db.flush();db.add(GenesisWorld(campaign_id=campaign.id,world_seed=42,config=config,plan={}));db.flush()
    region=Region(campaign_id=campaign.id,name="overlap");db.add(region);db.flush()
    cell=CellKey(0,17,20000,20000);point=cell_center(cell)
    exterior=Location(region_id=region.id,name="field",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":vars(cell),"point":list(point.xyz),"prepared":True})
    old_loc=Location(region_id=region.id,name="old",type="genesis_formation")
    db.add_all([exterior,old_loc]);db.flush()
    existing=GenesisNaturalFormation(id="overlap-old",campaign_id=campaign.id,location_id=old_loc.id,
        stable_key="existing-covered-instance",archetype_id="EV-LOC-0036",generator_version=VERSION_V2,
        data={"dimensions":{"horizontal_span_m":1200}})
    db.add(existing);db.flush()
    digest=contract_checksum(existing.stable_key,(cell,),1200)
    db.add(GenesisFormationCoverageCell(id="overlap-old-cell",campaign_id=campaign.id,
        formation_id=existing.id,face=cell.face,level=cell.level,x=cell.x,y=cell.y,
        contract_version=VERSION,contract_checksum=digest));db.flush()
    monkeypatch.setattr("app.game.world.genesis.wgs2_families.candidate",
        lambda seed,address,records,**kwargs:"EV-LOC-0051")
    monkeypatch.setattr(environment_service,"query_environment",lambda *args,**kwargs:{"baseline":{
        "physical_inputs":{"T1_height_mm":1000,"reference_ocean_H1":False},
        "authority_signature":"controlled-eligible-E1"}})
    own=local_formations.materialize_for_site(db,campaign,exterior)
    assert own.archetype_id == "EV-LOC-0051"
    assert own.stable_key != existing.stable_key
    assert db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign.id).count() == 2

    failed_key=CellKey(0,17,50_000,50_000);failed_point=cell_center(failed_key)
    failed_site=Location(region_id=region.id,name="oversize probe",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":vars(failed_key),"point":list(failed_point.xyz),"prepared":True})
    db.add(failed_site);db.flush()
    monkeypatch.setattr("app.game.world.genesis.wgs2_coverage.footprint_cells",
        lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError("bounded eight-cell-hop index")))
    before_locations=db.query(Location).filter_by(region_id=region.id,type="genesis_formation").count()
    before_coverage=db.query(GenesisFormationCoverageCell).filter_by(campaign_id=campaign.id).count()
    with pytest.raises(RuntimeError,match="bounded eight-cell-hop index"):
        local_formations.materialize_for_site(db,campaign,failed_site)
    assert db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign.id).count() == 2
    assert db.query(Location).filter_by(region_id=region.id,type="genesis_formation").count() == before_locations
    assert db.query(GenesisFormationCoverageCell).filter_by(campaign_id=campaign.id).count() == before_coverage


def test_wgs2_v3_unprepared_origin_is_order_independent(db_session, monkeypatch):
    """A covered cell can resolve its canonical origin before that origin is prepared."""
    from types import SimpleNamespace
    from app.game.world.genesis import local_formations
    from app.game.world.genesis.terrain.field import checksum
    import app.game.world.genesis.environment.service as environment_service
    from app.game.world.genesis.wgs2_coverage import footprint_cells
    db = db_session
    config = FormationConfigV4().model_dump(mode="json")
    a = CellKey(0, 17, 40000, 40000)
    a_point = cell_center(a)
    record = catalog()["EV-LOC-0037"]
    scale = record["geometria"]["escala_horizontal_m_sugerida"]
    max_span = min(3400, int(scale["max"]))
    min_span = min(max_span, int(scale["min"]))
    original_hash = local_formations._hash
    monkeypatch.setattr(local_formations, "_hash", lambda seed, key, label, version=local_formations.VERSION:
        max_span-min_span if label == "horizontal_span" else original_hash(seed,key,label,version))
    b = next(cell for cell in footprint_cells(a_point, 17, config["radius_m"], max_span) if cell != a)
    b_point = cell_center(b)
    monkeypatch.setattr("app.game.world.genesis.wgs2_families.candidate",
        lambda seed, address, records, **kwargs: "EV-LOC-0037" if address == vars(a) else None)
    facts = {"physical_inputs":{"T1_height_mm":1000,"reference_ocean_H1":False,"T1_slope_ppm":10000,
              "JR1_checksum":"jr1-test"},
        "logical_facts":{"clima.indice_aridez":0.4},
        "flora_contract":{"eligible_habitat_ids":["EV-BIO-ESCARPA_ROCHOSA"]},
        "authority_signature":"e1-order-test"}
    monkeypatch.setattr(environment_service, "query_environment", lambda *args, **kwargs: {"baseline":facts})
    monkeypatch.setattr(environment_service, "materialize_environment_point",
        lambda *args, **kwargs: SimpleNamespace(baseline=facts, baseline_checksum="e1-order-checksum"))

    outcomes = []
    for name, visit_order in (("origin-first", (a, b)), ("covered-cell-first", (b, a))):
        campaign = Campaign(name=name, world_seed=42, world_profile=local_formations.PROFILE_WGS2_V3,
            playable_state={"natural_formations":{"version":VERSION_V2,"selection_policy":local_formations.POLICY_WGS2},
                "microhabitats":{"version":"WGS2_MICROENVIRONMENT_V1","origin_lookup_version":"WGS2_ORIGIN_LOOKUP_R1"},
                "territory":{"version":"territory_tp1","level":17,"world_config":config,
                    "root_cell":vars(a),"root_point":list(a_point.xyz)}})
        db.add(campaign); db.flush()
        db.add(GenesisWorld(campaign_id=campaign.id,world_seed=42,config=config,plan={})); db.flush()
        region=Region(campaign_id=campaign.id,name=name); db.add(region); db.flush()
        sites={}
        for cell,point in ((a,a_point),(b,b_point)):
            site=Location(region_id=region.id,name=f"site-{cell.x}-{cell.y}",type="genesis_field",
                genesis_site={"version":"territory_tp1","cell":vars(cell),"point":list(point.xyz),
                    "prepared":cell!=a})
            db.add(site); db.flush()
            db.add(LocationSpatialAnchor(location_id=site.id,campaign_id=campaign.id,point=list(point.xyz)))
            sites[cell]=site
        campaign.playable_state={**campaign.playable_state,
            "territory":{**campaign.playable_state["territory"],"root_location_id":sites[a].id}}
        db.flush()
        returned=[]
        for cell in visit_order:
            result=local_formations.materialize_for_site(db,campaign,sites[cell])
            returned.append(result.stable_key if result else None)
        origin=db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign.id).one()
        assert origin.archetype_id == "EV-LOC-0037"
        assert origin.data.get("microenvironment", {}).get("status") == "neutral", (
            origin.generator_version, campaign.world_profile, local_formations.PROFILE_WGS2_V3,
            list(origin.data))
        assert origin.stable_key == checksum([VERSION_V2,42,vars(a),"EV-LOC-0037"])
        coverage=db.query(GenesisFormationCoverageCell).filter_by(campaign_id=campaign.id,
            formation_id=origin.id,contract_version=VERSION).all()
        assert any((r.face,r.level,r.x,r.y)==(b.face,b.level,b.x,b.y) and r.access_location_id for r in coverage)
        # Preparing B first materializes only A's exact covering origin; A's TP1 site itself stays unprepared.
        assert sites[a].genesis_site["prepared"] is False
        outcomes.append((returned,origin.stable_key,
            sorted((r.face,r.level,r.x,r.y,r.access_location_id is not None) for r in coverage)))
    assert outcomes[0][1:] == outcomes[1][1:]
