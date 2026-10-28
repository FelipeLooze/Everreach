"""WGS3.1 reads the single finite formation stock at real seed-42 sites."""
import pytest

from app.db.models.campaign import Campaign
from app.db.models.location import Location
from app.db.models.region import Region
from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_natural_formations import (GenesisLocalWaterBody,
    GenesisNaturalFormation, GenesisFormationCoverageCell)
from app.db.models.world_spatial import LocationSpatialAnchor
from app.game.character.service import create_character
from app.game.world.genesis import local_formations
from app.game.world.genesis.local_water import PROFILE, VERSION, contract, public_facts, current_place_fact
from app.game.world.genesis.sphere_topology import CellKey, cell_center
from app.game.world.genesis.vegetation.microhabitat import ORIGIN_LOOKUP_VERSION, VERSION as MICRO_VERSION
from app.game.world.genesis.vegetation.microhabitat_canonical import RESOLUTION_VERSION
from app.schemas.campaign import CampaignCreateRequest
from scripts.prove_vegetation import prepare
from scripts.validate_vegetation import inputs_vg1


def test_profile_is_explicit_and_water_projection_has_no_duplicate_stock():
    assert CampaignCreateRequest(name="Water", world_seed=42, world_profile=PROFILE).world_profile == PROFILE
    assert VERSION == "WGS3_LOCAL_WATER_R1"


def test_real_spring_identity_coverage_state_and_campaign_isolation(db_session, monkeypatch):
    sources = inputs_vg1(42)
    db = db_session
    cid = prepare(db, sources)
    campaign = db.get(Campaign, cid)
    world = db.get(GenesisWorld, cid)
    campaign.world_profile = PROFILE
    cell = CellKey(0,17,100000,30000)
    point = cell_center(cell)
    evidence = sources.environment.sample(point)
    assert local_formations.evaluate_context_v2("EV-LOC-0068", evidence, world.config["sea_level_m"])["accepted"]
    campaign.playable_state = {"natural_formations":{
        "version":local_formations.VERSION_WGS2_V2,
        "selection_policy":local_formations.POLICY_WGS2},
        "microhabitats":{"version":MICRO_VERSION,
            "origin_lookup_version":ORIGIN_LOOKUP_VERSION,
            "canonical_resolution_version":RESOLUTION_VERSION},
        "local_water":{"version":VERSION,"collection_enabled":False},
        "territory":{"version":"territory_tp1","level":17,"world_config":world.config}}
    region=Region(campaign_id=cid,name="Source field");db.add(region);db.flush()
    exterior=Location(region_id=region.id,name="Field",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":vars(cell),
                      "point":list(point.xyz),"prepared":True})
    db.add(exterior);db.flush()
    db.add(LocationSpatialAnchor(location_id=exterior.id,campaign_id=cid,point=list(point.xyz)))
    monkeypatch.setattr("app.game.world.genesis.wgs2_families.candidate",
        lambda seed,address,records,**kw: "EV-LOC-0068" if address == vars(cell) else None)
    original_hash=local_formations._hash
    monkeypatch.setattr(local_formations,"_hash",lambda seed,key,label,version=local_formations.VERSION:
        2285 if label == "horizontal_span" else original_hash(seed,key,label,version))
    formation=local_formations.materialize_for_site(db,campaign,exterior,_skip_origin_lookup=True)
    assert formation and formation.archetype_id == "EV-LOC-0068"
    assert db.query(GenesisLocalWaterBody).filter_by(campaign_id=cid).count() == 1
    state=contract(db,formation)
    assert state["source_type"] == "finite_local_spring"
    assert state["available_litres"] == state["capacity_litres"] == 12000
    assert state["volume_unit"] == "litre" and state["physical_water_present"]
    assert not state["collectable"] and not state["flow_confirmed"] and not state["recharge_authorized"]
    assert state["coverage"]["radius_m"] > 0
    public=public_facts(state)
    assert "point" not in public and "origin_authority" not in public
    actor=create_character(db,cid,"Explorer",None,None)
    actor.location_id=formation.location_id
    inspected=local_formations.inspect_current(db,actor.id)
    assert inspected["water_source"] == public
    assert inspected["water"] is None
    assert local_formations.interact_current(db,actor.id)["water_source"] == public
    from statistics import median
    from time import perf_counter
    contract_ms=[];inspect_ms=[]
    for _ in range(25):
        start=perf_counter();contract(db,formation);contract_ms.append((perf_counter()-start)*1000)
        start=perf_counter();local_formations.inspect_current(db,actor.id);inspect_ms.append((perf_counter()-start)*1000)
    print(f"WGS3_WATER_PERF contract_median_ms={median(contract_ms):.3f} inspect_median_ms={median(inspect_ms):.3f}")
    coverage=db.query(GenesisFormationCoverageCell).filter_by(formation_id=formation.id).all()
    other=next((row for row in coverage if
        (row.face,row.level,row.x,row.y) != (cell.face,cell.level,cell.x,cell.y)),None)
    assert other is not None
    neighbor=CellKey(other.face,other.level,other.x,other.y)
    next_point=cell_center(neighbor)
    adjacent=Location(region_id=region.id,name="Adjacent field",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":vars(neighbor),
                      "point":list(next_point.xyz),"prepared":True})
    db.add(adjacent);db.flush()
    db.add(LocationSpatialAnchor(location_id=adjacent.id,campaign_id=cid,point=list(next_point.xyz)))
    local_formations._ensure_wgs2_coverage_access(db,campaign,adjacent,formation,other)
    actor.location_id=other.access_location_id
    assert local_formations.inspect_current(db,actor.id)["water_source"]["source_key"] == state["source_key"]
    assert db.query(GenesisLocalWaterBody).filter_by(campaign_id=cid).count() == 1
    db.commit();db.expire_all()
    formation=db.get(GenesisNaturalFormation,formation.id)
    assert contract(db,formation) == state
    row=db.get(GenesisLocalWaterBody,formation.id)
    row.stored_litres=0;row.revision+=1;db.commit();db.expire_all()
    dry=contract(db,db.get(GenesisNaturalFormation,formation.id))
    assert not dry["physical_water_present"] and dry["available_litres"] == 0
    assert dry["source_key"] == state["source_key"] and dry["signature"] != state["signature"]
    assert "sem água" in current_place_fact(db,cid,actor.location_id)
    assert "fissura" in local_formations.inspect_current(db,actor.id)["features"][0]
    assert "estoque local" in local_formations.inspect_current(db,actor.id)["features"][0]
    from app.game.perception.service import observe_surroundings
    dry_observation=observe_surroundings(db,actor)
    assert any("sem água" in feature for feature in dry_observation.features)
    assert db.query(GenesisLocalWaterBody).filter_by(campaign_id=cid).count() == 1
    second=Campaign(name="Independent stock",world_seed=42,world_profile=PROFILE)
    db.add(second);db.flush()
    db.add(GenesisWorld(campaign_id=second.id,world_seed=42,config=world.config,plan={}))
    db.flush()
    second_region=Region(campaign_id=second.id,name="Same canonical geography")
    db.add(second_region);db.flush()
    second_location=Location(region_id=second_region.id,name="Spring",type="genesis_formation")
    db.add(second_location);db.flush()
    db.add(LocationSpatialAnchor(location_id=second_location.id,campaign_id=second.id,
                                 point=list(formation.data["point"])))
    second_formation=GenesisNaturalFormation(id="second-spring",campaign_id=second.id,
        location_id=second_location.id,stable_key=formation.stable_key,
        archetype_id=formation.archetype_id,generator_version=formation.generator_version,
        data=formation.data)
    db.add(second_formation);db.flush()
    db.add(GenesisLocalWaterBody(formation_id=second_formation.id,campaign_id=second.id,
        capacity_litres=12000,stored_litres=12000,revision=0,
        source_origin=row.source_origin));db.flush()
    second_state=contract(db,second_formation)
    assert second_state["source_key"] == dry["source_key"]
    assert second_state["available_litres"] == 12000
    assert second_state["signature"] != dry["signature"]


def test_missing_stock_is_rejected_without_inventing_water(db_session):
    db=db_session
    campaign=Campaign(name="Missing",world_seed=42,world_profile=PROFILE)
    db.add(campaign);db.flush()
    region=Region(campaign_id=campaign.id,name="Missing water");db.add(region);db.flush()
    location=Location(region_id=region.id,name="Spring",type="genesis_formation")
    db.add(location);db.flush()
    formation=GenesisNaturalFormation(id="missing-water",campaign_id=campaign.id,
        location_id=location.id,stable_key="missing",archetype_id="EV-LOC-0068",
        generator_version="natural_formations_wgs2_v2",data={})
    db.add(formation);db.flush()
    with pytest.raises(ValueError,match="lacks its persisted stock"):
        contract(db,formation)
    formation.archetype_id="EV-LOC-0051"
    assert contract(db,formation) is None
