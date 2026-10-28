"""R1 derived gameplay estimates. No dataset edit or vegetation recalibration.

One unit is the named raw part/portion delivered, never an unlisted product.
Masses are fresh material game estimates, not scientific measurements.
"""
from collections import Counter
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.db.models.world_plant_resources import GenesisPlantResources
from .catalog import load_flora_catalog
from .config import TYPE_HEIGHT_CM
from ..terrain.field import checksum

# Fresh standing biomass at reference height (cm); deliberately coarse game balance.
BODY={"arvore":(2000,400000000),"arbusto":(150,2500000),"flor":(40,35000),"erva":(60,90000),
    "graminea":(80,35000),"samambaia":(100,180000),"trepadeira":(200,250000),"musgo":(5,12000),
    "liquen":(3,8000),"fungo":(15,60000),"junco":(120,80000),"alga":(25,25000),"consorcio_simbiotico":(3,6000)}
# Target portion mg, maximum represented units, anatomical pool.
PARTS={"folhas":(1200,48,"vegetative"),"petalas":(250,12,"reproductive"),"frutos":(25000,16,"reproductive"),
    "sementes":(500,16,"reproductive"),"raiz":(10000,1,"subterranean"),"tuberculo":(35000,5,"subterranean"),
    "ramos":(25000,20,"vegetative"),"fibras":(1500,20,"vegetative"),"caules":(8000,10,"vegetative"),"casca":(2000,10,"vegetative"),
    "madeira":(250000,12,"vegetative"),"esporos":(50,8,"reproductive"),"tufo":(2000,6,"vegetative"),
    "filamentos":(500,6,"vegetative"),"frondes":(3000,12,"vegetative"),"corpo_frutifero":(8000,8,"vegetative"),
    "fragmentos":(500,6,"vegetative"),"po":(200,6,"vegetative"),"talos":(2000,12,"vegetative"),
    "pigmento_bruto":(500,6,"vegetative"),"propagulos":(100,6,"reproductive"),"amostra_colonia":(200,4,"vegetative"),
    "tecido_fungico":(800,6,"vegetative"),"fragmento_talo":(300,6,"vegetative"),"fragmento_lamina":(500,6,"vegetative"),"talo":(1000,8,"vegetative")}
PROCESSING={"po":"dry_loose_material_or_processing_not_confirmed","pigmento_bruto":"extraction_requires_future_processing"}
AVAILABILITY={"version":1,"periods":{"madrugada":[0,5],"manha":[6,12],"tarde":[12,18],"noite":[20,24]},
    "twilight_hours":[5,18,19],"year_round_activity":"current_C3_period_above_freezing_and_positive_W1_ET"}


class PartOverride(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid",strict=True)
    unit_mass_mg: int|None=Field(default=None,gt=0,le=10**9)
    max_units: int|None=Field(default=None,ge=0,le=10000)
    rationale: str=Field(min_length=8,max_length=512)


class ResourceConfigR1(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid",strict=True)
    resource_version: Literal[1]=1
    profile: Literal["botanical_gameplay_estimates_r1"]="botanical_gameplay_estimates_r1"
    inventory_mg_per_weight_unit: int=Field(default=1000000,gt=0,le=10**12)
    collect_minutes: int=Field(default=3,ge=1,le=60)
    overrides: dict[str,PartOverride]=Field(default_factory=dict)

    @field_validator("resource_version",mode="before")
    @classmethod
    def strict_version(cls,v):
        if type(v) is not int:raise ValueError("Explicit resource version required")
        return v


def derive(species,height_cm,config=None):
    config=config or ResourceConfigR1();height=max(1,height_cm);ref,base=BODY[species.kind]
    biomass=max(200,base*height*height//(ref*ref))
    raw=species.parts();groups=Counter(PARTS[p["parte"]][2] for p in raw if p["parte"] in PARTS)
    pools={"vegetative":max(1,biomass*30//100),"reproductive":max(1,biomass*12//100),"subterranean":max(1,biomass*25//100)}
    records={}
    for p in raw:
        label=p["parte"]
        if label not in PARTS:
            records[p["id"]]={"state":"pending","reason":"unknown_anatomical_part"};continue
        target,limit,pool=PARTS[label]
        # Type/height and stable species morphology; rarity never affects mass.
        variation=800+int(checksum([species.id,p["id"],"R1_morphology"])[:8],16)%401
        portion=target*max(35,min(250,height*100//ref))*variation//100000
        if label=="raiz":portion=max(1,biomass*15//100)
        budget=pools[pool]//groups[pool]
        mass=max(1,min(portion,max(1,budget)))
        units=max(1,min(limit*max(35,min(200,height*100//ref))//100,budget//mass))
        override=config.overrides.get(p["id"])
        if override:
            mass=override.unit_mass_mg if override.unit_mass_mg is not None else mass
            units=override.max_units if override.max_units is not None else units
        if mass*units>budget:raise ValueError("Derived/override yield exceeds shared tissue allocation")
        historical=p.get("quantidade_max")
        per_action=historical if type(historical) is int and historical>0 else min(5,max(1,units))
        preserve=p.get("colheita_preserva_individuo")
        if preserve is None:preserve=label not in ("raiz","tufo","amostra_colonia","talo")
        records[p["id"]]={"part_id":p["id"],"item_id":p["item_id"],"part":label,"pool":pool,
            "unit_mass_mg":mass,"max_units":units,"per_action_max":per_action,
            "preserves_individual":bool(preserve) and label!="raiz","state":"pending" if label in PROCESSING else "usable",
            "reason":PROCESSING.get(label),"unit_semantics":"whole_root" if label=="raiz" else "named_raw_part_or_small_portion",
            "maturity_required":"fruiting" if label in ("frutos","sementes","esporos","propagulos","corpo_frutifero") else "flowering" if label in ("petalas","flores") else "adult",
            "historical_node_stock_not_a_runtime_cap":species.stock,"estimate_not_measurement":True}
    recovery=([90,120] if species.magic=="excepcional" else [5,7] if species.rarity<35 else [10,14] if species.rarity<60 else
        [20,30] if species.rarity<80 else [45,60])
    return {"species_id":species.id,"organism_type":species.kind,"height_cm":height,"standing_biomass_mg":biomass,
        "pools_mg":pools,"parts":records,"method":"type_height_squared_anatomical_fractions_portion_profiles_r1",
        "provenance":"v22_canonical_parts_and_height_plus_versioned_game_design_estimates",
        "future_recovery":{"proposed_days":recovery,"active":False,"requires_live_individual_and_future_event":True,"new_individual_growth_is_separate":True},
        "profile_checksum":checksum([species.id,height,config.model_dump(mode="json"),records,pools])}


def initialize_resources(db,campaign_id,config=None,*,experimental=False):
    from .service import context
    if experimental is not True:raise ValueError("Explicit experimental R1 activation required")
    v=context(db,campaign_id)
    if v.config.vegetation_version!=2:raise ValueError("R1 requires unchanged Vg2; no legacy migration")
    cfg=config or ResourceConfigR1();cat=load_flora_catalog()
    ids={p["id"] for s in cat.species.values() for p in s.parts()}
    if set(cfg.overrides)-ids:raise ValueError("Unknown override part")
    d={"kind":"plant_resources_r1","version":1,"vegetation_signature":v.signature,"flora_sha256":cat.source_hash,
        "config":cfg.model_dump(mode="json"),"body_rules":BODY,"part_rules":PARTS,"processing_blocks":PROCESSING,"availability_policy":AVAILABILITY,
        "mass_provenance":"gameplay_estimates_not_measured","inventory_conversion":"explicit_mg_per_existing_weight_unit",
        "legacy_policy":"existing_individuals_and_item_definitions_unchanged"}
    # JSON representation is the persistence contract (tuples become lists).
    import json
    d=json.loads(json.dumps(d));sig=checksum(d)[:24]
    old=db.get(GenesisPlantResources,campaign_id)
    if old:
        header(db,campaign_id,v)
        if old.descriptor!=d:raise ValueError("Cannot reconfigure established R1")
        return old
    row=GenesisPlantResources(campaign_id=campaign_id,signature=sig,descriptor=d,descriptor_checksum=checksum(d))
    db.add(row);db.flush();return row


def header(db,cid,v):
    row=db.get(GenesisPlantResources,cid,populate_existing=True)
    if row is None:return None
    d=row.descriptor
    if (checksum(d)!=row.descriptor_checksum or checksum(d)[:24]!=row.signature or type(d.get("version")) is not int or d.get("version")!=1 or d.get("kind")!="plant_resources_r1" or
        d["vegetation_signature"]!=v.signature or d["flora_sha256"]!=v.catalog.source_hash or
        d["body_rules"]!={k:list(a) for k,a in BODY.items()} or d["part_rules"]!={k:list(a) for k,a in PARTS.items()} or d["processing_blocks"]!=PROCESSING or d.get("availability_policy")!=AVAILABILITY):
        raise ValueError("R1 authority corrupted or changed; refusing regeneration")
    return row


def founding_baseline(db,cid,v,b,existing):
    if existing is not None and "resource_signature" not in existing.baseline:return b
    row=header(db,cid,v)
    if row is None:
        if existing is not None and "resource_signature" in existing.baseline:raise ValueError("Missing persisted R1 authority")
        return b
    config=ResourceConfigR1.model_validate(row.descriptor["config"])
    sp=v.catalog.species[b["species_id"]];profile=derive(sp,b["height_cm"],config)
    stock={}
    for pid,p in profile["parts"].items():
        ready=p["state"]=="usable" and (p["maturity_required"]=="adult" or p["maturity_required"]==b["phenology"])
        stock[pid]=p["max_units"] if ready else 0
    return {**b,"initial_part_stock":stock,"stock_calibration":"R1_derived_gameplay_estimates",
        "resource_signature":row.signature,"resource_profile":profile,"inventory_mg_per_weight_unit":config.inventory_mg_per_weight_unit}


def initial_state(b,state):
    if "resource_signature" not in b:return state
    return {**state,"tissue_remaining_mg":dict(b["resource_profile"]["pools_mg"]),"exported_mass_mg":0,
        "discarded_mass_mg":0,"last_harvest_world_minute":None,"last_removed_part":None,"regrowth_scheduled":False}


def consume(b,state,part_id,quantity,world_minute):
    from copy import deepcopy
    state=deepcopy(state);p=b["resource_profile"]["parts"][part_id];mass=p["unit_mass_mg"]*quantity
    if quantity>p["per_action_max"]:raise ValueError("Quantity exceeds the canonical/procedural per-action yield")
    if state["part_stock"][part_id]<quantity or state["tissue_remaining_mg"][p["pool"]]<mass:
        raise ValueError("Insufficient finite plant stock or tissue")
    state["part_stock"][part_id]-=quantity;state["tissue_remaining_mg"][p["pool"]]-=mass
    state["exported_mass_mg"]+=mass;state["revision"]+=1
    state["last_harvest_world_minute"]=world_minute;state["last_removed_part"]=part_id
    if not p["preserves_individual"]:
        state["alive"]=False;state["discarded_mass_mg"]+=sum(state["tissue_remaining_mg"].values())
        state["tissue_remaining_mg"]={k:0 for k in state["tissue_remaining_mg"]};state["part_stock"]={k:0 for k in state["part_stock"]}
    return state,mass


def validate_state(b,state):
    if "resource_signature" not in b:return
    if 'life' in state:
        from .lifecycle import validate
        validate(b,state);return
    profile=b["resource_profile"];pools=profile["pools_mg"]
    if set(state["tissue_remaining_mg"])!=set(pools):raise ValueError("R1 tissue pool mismatch")
    values=[*state["tissue_remaining_mg"].values(),state["exported_mass_mg"],state["discarded_mass_mg"]]
    if any(type(v) is not int or v<0 for v in values) or sum(values)!=sum(pools.values()):
        raise ValueError("R1 mass conservation mismatch")
    for pool,left in state["tissue_remaining_mg"].items():
        reserved=sum(p["unit_mass_mg"]*state["part_stock"][pid] for pid,p in profile["parts"].items() if p.get("pool")==pool)
        if reserved>left:raise ValueError("Parts double allocate remaining tissue")


def available_now(db,cid,sampler,individual,part,clock):
    from app.game.time.clock import current_season
    from ..sphere_topology import SurfacePoint
    season=current_season(db,cid).value
    names={"SPRING":"primavera","SUMMER":"verao","AUTUMN":"outono","WINTER":"inverno"}
    seasons=part["disponibilidade"]["estacoes"]
    if names[season] not in seasons:
        if "todo_ano_condicionado_a_atividade_biologica" not in seasons:return False,"outside_catalog_season"
        index={"SPRING":0,"SUMMER":1,"AUTUMN":2,"WINTER":3}[season]
        point=SurfacePoint(*individual.baseline["point"]);e=sampler.environment.sample(point);w=sampler.water_facts(point)
        temperature=e["physical_inputs"]["C3_seasons"][index]["temperature_centi_c"]
        et=sampler.water.solution.periods[index]["fluxes"]["evapotranspiration"][w["node"]]
        if temperature<=0 or et<=0:return False,"seasonal_biological_activity_not_supported"
    period=("crepusculo" if clock.hour in AVAILABILITY["twilight_hours"] else
        next((k for k,(a,b) in AVAILABILITY["periods"].items() if a<=clock.hour<b),None))
    return (True,None) if period in part["disponibilidade"]["periodos_do_dia"] else (False,"outside_catalog_day_period")
