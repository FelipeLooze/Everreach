"""Experimental opt-in persistence. The caller owns commit/rollback.

Only technical APIs are added. No public endpoint, travel edge or discovery is created.
"""
from collections import OrderedDict,Counter
from copy import deepcopy
from math import isqrt
from sqlalchemy import update
from app.db.models.world_vegetation import (GenesisVegetationPlan,GenesisVegetationCommunity,
    GenesisPlantIndividual,GenesisPlantAction,GenesisBotanicalToolCertificate)
from app.db.models.character import Character
from app.db.models.world_spatial import LocationSpatialAnchor
from app.db.models.skill import CharacterSkill
from app.db.models.item import ItemDefinition,ItemInstance
from app.core.enums import ToolCapability,ItemLocationType,ItemOwnerType
from app.game.items.service import create_item_instance,move_item_instance,set_item_owner
from app.game.items.tools import validate_character_tool_use
from app.game.time.clock import get_world_time,current_season
from ..environment.service import get_environment_sampler,materialize_environment_point,query_environment
from ..water.service import get_water_plan
from ..terrain.field import checksum
from ..terrain.address import point_on_face
from ..sphere_topology import SurfacePoint
from ..sphere_metric import distance_m
from .config import VegetationConfig,parse_vegetation_config,make_vegetation_sampler
from .field import VegetationSampler,eligibility,physiognomy

_cache=OrderedDict()


def initialize_vegetation(db,campaign_id,config=None,*,experimental=False):
    if experimental is not True:raise ValueError("Vg1 requires explicit experimental activation")
    existing=db.get(GenesisVegetationPlan,campaign_id)
    if existing:
        sampler=context(db,campaign_id)
        if config is not None and config!=sampler.config:raise ValueError("Cannot reconfigure established vegetation")
        return existing
    sampler=make_vegetation_sampler(get_environment_sampler(db,campaign_id),get_water_plan(db,campaign_id),config)
    row=GenesisVegetationPlan(campaign_id=campaign_id,signature=sampler.signature,descriptor=sampler.descriptor,
        descriptor_checksum=checksum(sampler.descriptor),write_epoch=0)
    db.add(row);db.flush();_remember(sampler)
    return row


def _remember(sampler):
    _cache[sampler.signature]=sampler
    while len(_cache)>2:_cache.popitem(last=False)


def context(db,campaign_id):
    row=db.get(GenesisVegetationPlan,campaign_id,populate_existing=True)
    if row is None:raise ValueError("Initialize Vg1 explicitly; no autoactivation")
    if checksum(row.descriptor)!=row.descriptor_checksum or checksum(row.descriptor)[:24]!=row.signature:
        raise ValueError("Vg1 descriptor corrupted; refusing regeneration")
    e,w=get_environment_sampler(db,campaign_id),get_water_plan(db,campaign_id)
    d=row.descriptor
    if (e.signature!=d["E1_signature"] or checksum(e.descriptor)!=d["E1_descriptor_checksum"] or
            w.signature!=d["water_signature"] or checksum(w.to_dict())!=d["water_checksum"]):
        raise ValueError("Vg1 upstream authority changed; explicit reconciliation required")
    sampler=_cache.get(row.signature)
    if sampler is None:
        sampler=make_vegetation_sampler(e,w,parse_vegetation_config(d["config"]))
        _remember(sampler)
    if sampler.descriptor!=d:raise ValueError("Vg1 source/config mismatch")
    return sampler


def _fence(db,cid):
    if db.get_bind().dialect.name!="sqlite":raise ValueError("Vg1 writer fence validated for SQLite only")
    db.flush()
    db.execute(update(GenesisVegetationPlan).where(GenesisVegetationPlan.campaign_id==cid).
        values(write_epoch=GenesisVegetationPlan.write_epoch+1),execution_options={"synchronize_session":False})


def _validate_community(row,sampler):
    b=row.baseline
    if (checksum(b)!=row.baseline_checksum or b["authority_signature"]!=sampler.signature or
            b["community_id"]!=row.community_id or sampler.address(SurfacePoint(*b["point"]))[1]!=row.community_id):
        raise ValueError("Established community corrupted; refusing regeneration")
    local = b.get("microenvironment_context")
    if local is not None and (local.get("version") != "WGS2_MICROENVIRONMENT_V1"
            or local.get("contract_signature") != local.get("evidence_signature")):
        raise ValueError("Established WGS2 microenvironment snapshot corrupted")


def microenvironment_context(db,campaign_id,sampler,point):
    if sampler.config.policy == "regional_canopy_wgs2_canonical_v1":
        from .microhabitat_canonical import resolve
        return resolve(db,campaign_id,point,sampler)
    if sampler.config.policy != "regional_canopy_wgs2_microhabitat_v1":
        return None
    from .microhabitat import resolve
    return resolve(db,campaign_id,point)


def apply_local_environment(environment,local_context):
    if local_context is None:
        return environment
    from .microhabitat import apply_to_environment
    return apply_to_environment(environment,local_context)


_UNRESOLVED_MICROENVIRONMENT=object()


def eligibility_at(db,campaign_id,sampler,species,point,*,_local_context=_UNRESOLVED_MICROENVIRONMENT):
    from .field import eligibility
    local_context=(microenvironment_context(db,campaign_id,sampler,point)
                   if _local_context is _UNRESOLVED_MICROENVIRONMENT else _local_context)
    environment=apply_local_environment(sampler.environment.sample(point),local_context)
    return eligibility(species,environment,sampler.water_facts(point))


def _physical_current(db,cid,row,sampler=None):
    # Reuse E1's checks for terrain, JR1 and J1 changes. Never silently resample a changed world.
    query_environment(db,cid,SurfacePoint(*row.baseline["point"]),_sampler=sampler.environment if sampler is not None else None)


def sample_initial_community(db,campaign_id,sampler,point):
    """Read a saved community, or preview its canonical V4 baseline without writes."""
    if sampler.config.policy != "regional_canopy_wgs2_canonical_v1":
        return sampler.sample(point)
    cell,identifier=sampler.address(point)
    row=db.get(GenesisVegetationCommunity,(campaign_id,identifier))
    if row is not None:
        _validate_community(row,sampler)
        _physical_current(db,campaign_id,row,sampler)
        return deepcopy(row.baseline)
    local_context=microenvironment_context(db,campaign_id,sampler,cell.point(1,1,2))
    return sampler.sample(point,microenvironment=local_context)


def materialize_community(db,campaign_id,point,*,_sampler=None):
    sampler=_sampler if _sampler is not None else context(db,campaign_id);identifier=sampler.address(point)[1]
    _fence(db,campaign_id)
    with db.begin_nested():
        row=db.get(GenesisVegetationCommunity,(campaign_id,identifier),populate_existing=True)
        cell,_=sampler.address(point);center=cell.point(1,1,2)
        # Preserve V3's existing validation on revisits. V4 keeps its saved
        # baseline without resolving newly visible physical sources again.
        local_context=(microenvironment_context(db,campaign_id,sampler,center)
            if row is None or sampler.config.policy != "regional_canopy_wgs2_canonical_v1" else None)
        if row is None:
            b=(sampler.sample(point,microenvironment=local_context)
               if sampler.config.policy in ("regional_canopy_wgs2_microhabitat_v1", "regional_canopy_wgs2_canonical_v1") else sampler.sample(point))
            center=SurfacePoint(*b["point"])
            materialize_environment_point(db,campaign_id,center,_sampler=sampler.environment)
            b["persisted"]=True
            row=GenesisVegetationCommunity(campaign_id=campaign_id,community_id=identifier,baseline=b,baseline_checksum=checksum(b))
            db.add(row);db.flush()
        _validate_community(row,sampler)
        # A saved community is an immutable ecological snapshot. A formation
        # may become known later (for example, after the start site was first
        # materialized); that must not rewrite its population or invalidate a
        # revisit. New communities use the currently resolved local context.
        _physical_current(db,campaign_id,row,sampler)
        return row


def _individual_baseline(sampler,community,species_id,slot,*,_micro_lookup=None):
    b=community.baseline
    pop=next((p for p in b["populations"] if p["species_id"]==species_id),None)
    if pop is None or type(slot) is not int or not 0<=slot<pop["founder_count"]:
        raise ValueError("Individual must occupy a finite established founder slot")
    face,level,x,y=b["physical_address"]
    grid=1
    while grid*grid<pop["founder_count"]:grid*=2
    salt=int(checksum([pop["population_id"],"position"])[:16],16)
    index=(slot*(2*(salt//(grid*grid))+1)+salt)%(grid*grid)
    ix,iy=index%grid,index//grid
    point=point_on_face(face,2*x*grid+2*ix+1,2*y*grid+2*iy+1,2**(level+1)*grid)
    sp=sampler.catalog.species[species_id]
    local_context=_micro_lookup(point) if _micro_lookup is not None else None
    environment=apply_local_environment(sampler.environment.sample(point),local_context)
    state,why=eligibility(sp,environment,sampler.water_facts(point))
    if state!="eligible":raise ValueError("Founder slot microsite unsupported: "+str(why))
    identifier="vgi:"+checksum([pop["population_id"],slot])[:32]
    phenology=("vegetative","flowering","fruiting")[int(checksum(identifier)[:8],16)%3]
    stock={};remaining=sp.stock if type(sp.stock) is int and sp.stock>0 else 0
    for part in sp.parts():
        maximum=part.get("quantidade_max")
        calibration=getattr(sampler,"calibrations",{}).get(part["id"])
        if sampler.config.vegetation_version==2:
            maximum=calibration.max_mature_units if calibration else 0
            # Missing source stock is not guessed: only an explicitly reviewed,
            # pinned species/part measurement may authorize a new finite yield.
            if sp.stock is None:remaining=maximum
        phase_required=("fruiting" if part["parte"] in ("sementes","frutos","propagulos","esporos") else
            "flowering" if part["parte"] in ("petalas","flores") else None)
        amount=min(remaining,maximum) if type(maximum) is int and maximum>0 and (phase_required is None or phase_required==phenology) else 0
        stock[part["id"]]=amount;remaining-=amount
    result={"individual_id":identifier,"community_id":community.community_id,"population_id":pop["population_id"],
        "species_id":species_id,"slot":slot,"point":list(point.xyz),"height_cm":pop["height_cm"],
        "origin":sampler.config.founding,"maturity":"adult","phenology":phenology,"initial_part_stock":stock,
        "stock_calibration":("reviewed_species_part_mass_yield_v1" if sampler.config.vegetation_version==2 and any(stock.values()) else
            "pending_reviewed_mass_and_yield" if sampler.config.vegetation_version==2 else
            "nonnull_catalog_node_suggestion_bounded_by_part_max_v1" if sp.stock else "pending_catalog_stock"),
        "automatic_growth":False,"automatic_regrowth":False}
    if sampler.config.policy in ("regional_canopy_wgs2_microhabitat_v1", "regional_canopy_wgs2_canonical_v1"):
        result["microenvironment_context"]=local_context
    return result


def _validate_individual(row):
    if (checksum(row.baseline)!=row.baseline_checksum or row.baseline["individual_id"]!=row.individual_id or
            row.baseline["community_id"]!=row.community_id or checksum(row.state)!=row.state_checksum):
        raise ValueError("Individual state corrupted; refusing regeneration")
    initial=row.baseline["initial_part_stock"];state=row.state
    if (type(state.get("alive")) is not bool or set(state["part_stock"])!=set(initial) or
            any(type(v) is not int or not 0<=v<=(row.baseline['resource_profile']['parts'][k]['max_units'] if 'life' in state else initial[k]) for k,v in state["part_stock"].items()) or
            (not state["alive"] and any(state["part_stock"].values()))):
        raise ValueError("Invalid finite plant stock")
    from .resources import validate_state
    validate_state(row.baseline,row.state)


def materialize_individual(db,campaign_id,point,species_id,slot,*,_sampler=None,_community=None):
    # Internal look batches reuse the source context and parent already checked
    # under materialize_community's SQLite writer fence. Public callers validate afresh.
    sampler=_sampler if _sampler is not None else context(db,campaign_id)
    community=_community if _community is not None else materialize_community(db,campaign_id,point,_sampler=sampler)
    if community.campaign_id!=campaign_id:raise ValueError("Community campaign mismatch")
    _validate_community(community,sampler)
    pop=next((p for p in community.baseline["populations"] if p["species_id"]==species_id),None)
    if pop is None or type(slot) is not int or not 0<=slot<pop["founder_count"]:
        raise ValueError("Individual must occupy a finite established founder slot")
    identifier="vgi:"+checksum([pop["population_id"],slot])[:32]
    existing=db.get(GenesisPlantIndividual,(campaign_id,identifier),populate_existing=True)
    if existing is not None:
        # Existing individuals keep the local evidence snapshot under which
        # they were founded, even if a newly materialized formation now covers
        # their cell. Never regenerate a founder from a changed environment.
        _validate_individual(existing)
        if (existing.community_id!=community.community_id or
                existing.baseline.get("species_id")!=species_id or
                existing.baseline.get("slot")!=slot):
            raise ValueError("Persisted founder identity mismatch")
        query_environment(db,campaign_id,SurfacePoint(*existing.baseline["point"]),_sampler=sampler.environment)
        from .lifecycle import sync
        sync(db,campaign_id,existing,sampler)
        return existing
    b=_individual_baseline(sampler,community,species_id,slot,
        _micro_lookup=lambda q:microenvironment_context(db,campaign_id,sampler,q))
    with db.begin_nested():
        row=db.get(GenesisPlantIndividual,(campaign_id,b["individual_id"]),populate_existing=True)
        from .resources import founding_baseline,initial_state
        b=founding_baseline(db,campaign_id,sampler,b,row)
        if row is None:
            materialize_environment_point(db,campaign_id,SurfacePoint(*b["point"]),_sampler=sampler.environment)
            state=initial_state(b,{"alive":True,"part_stock":deepcopy(b["initial_part_stock"]),"revision":0})
            row=GenesisPlantIndividual(campaign_id=campaign_id,individual_id=b["individual_id"],community_id=community.community_id,
                baseline=b,baseline_checksum=checksum(b),state=state,state_checksum=checksum(state))
            db.add(row);db.flush()
        _validate_individual(row)
        if row.baseline!=b:raise ValueError("Founder descriptor changed; refusing regeneration")
        query_environment(db,campaign_id,SurfacePoint(*b["point"]),_sampler=sampler.environment)
        from .lifecycle import sync
        sync(db,campaign_id,row,sampler)
        return row


def query_community(db,campaign_id,point):
    sampler=context(db,campaign_id);identifier=sampler.address(point)[1]
    row=db.get(GenesisVegetationCommunity,(campaign_id,identifier),populate_existing=True)
    if row is None:raise ValueError("Community not materialized; read does not create populations")
    _validate_community(row,sampler)
    _physical_current(db,campaign_id,row)
    b=deepcopy(row.baseline);removed=Counter()
    for ind in db.query(GenesisPlantIndividual).filter_by(campaign_id=campaign_id,community_id=identifier):
        _validate_individual(ind)
        if not ind.state["alive"]:removed[ind.baseline["species_id"]]+=1
    for pop in b["populations"]:
        count=pop["founder_count"];pop["living_count"]=count-removed[pop["species_id"]]
        from .lifecycle import population_counts
        life_counts=population_counts(db,campaign_id,row,pop,sampler)
        if life_counts is None:pop["cover_ppm"]=pop["cover_ppm"]*pop["living_count"]//count
        else:
            pop['living_count'],fraction=life_counts
            pop['cover_ppm']=pop['cover_ppm']*fraction//1000000
            removed[pop['species_id']]=count-pop['living_count']
    b["cover_ppm"]=sum(p["cover_ppm"] for p in b["populations"])
    b["clearing_ppm"]=1000000-b["cover_ppm"]
    b["physiognomy"]=physiognomy([p for p in b["populations"] if p["living_count"]],b["cover_ppm"],b["source_evidence"]["temperature_c"])
    living=sorted((p for p in b["populations"] if p["living_count"]),key=lambda p:(-p["cover_ppm"],p["species_id"]))
    b["established"]=bool(living)
    b["dominant_species"]=living[0]["species_id"] if living else None
    b["secondary_species"]=[p["species_id"] for p in living[1:]]
    b["density_per_ha"]=int(sum(p["living_count"] for p in living)*10000/b["patch_area_m2"])
    b["strata_cover_ppm"]={k:sum(p["cover_ppm"] for p in living if ("canopy" if p["height_cm"]>=500 else "shrub" if p["height_cm"]>=100 else "ground")==k) for k in ("canopy","shrub","ground")}
    b["individuals_materialized"]=db.query(GenesisPlantIndividual).filter_by(campaign_id=campaign_id,community_id=identifier).count()
    b["removed_individuals"]=dict(removed)
    return b


def _present(db,cid,actor_id,individual,sampler):
    actor=db.get(Character,actor_id)
    if actor is None or actor.campaign_id!=cid or actor.status!="ALIVE" or actor.hp_current<=0:
        raise ValueError("A living actor in this campaign is required")
    anchor=db.get(LocationSpatialAnchor,actor.location_id) if actor.location_id else None
    if anchor is None or anchor.campaign_id!=cid:
        raise ValueError("Actor needs an actual spatially anchored location")
    if distance_m(sampler.environment.regional.terrain.plan.source.config,SurfacePoint(*anchor.point),SurfacePoint(*individual.baseline["point"]))>5:
        raise ValueError("Actor must be within five meters of the actual individual")
    return actor


def observe_individual(db,campaign_id,actor_id,individual_id,*,_sampler=None,_physical_checked=False):
    sampler=_sampler if _sampler is not None else context(db,campaign_id)
    row=db.get(GenesisPlantIndividual,(campaign_id,individual_id),populate_existing=True)
    if row is None:raise ValueError("Individual not materialized")
    _validate_individual(row);_present(db,campaign_id,actor_id,row,sampler)
    from .lifecycle import sync
    sync(db,campaign_id,row,sampler)
    if not _physical_checked:query_environment(db,campaign_id,SurfacePoint(*row.baseline["point"]))
    skill=db.query(CharacterSkill).filter_by(character_id=actor_id,skill_id="EV-PROF-BOT-001").first()
    identified=skill is not None and skill.mastery>=60
    sp=sampler.catalog.species[row.baseline["species_id"]]
    return {"individual_id":individual_id,"kind":sp.kind,"height_cm":row.state.get('life',{}).get('height_cm',row.baseline["height_cm"]),"alive":row.state["alive"],
        **({'maturity':row.state['life']['maturity'],'life_version':1} if 'life' in row.state else {}),
        "identified":identified,"species_id":sp.id if identified else None,"name":sp.name if identified else None,
        "magic_effects_confirmed":False,"edibility_confirmed":False}


def certify_botanical_tool(db,item_id,capabilities,*,experimental=False):
    """Trusted developer calibration only, not a player claim or inference from a name."""
    from app.db.models.tool import ItemToolProfile
    if experimental is not True or not capabilities or not all(isinstance(x,str) and x for x in capabilities):
        raise ValueError("Explicit experimental tool calibration required")
    profile=db.get(ItemToolProfile,item_id)
    if profile is None:raise ValueError("Existing physical tool profile required")
    cert={"version":1,"source":"explicit_experimental_botanical_calibration","capabilities":sorted(set(capabilities)),
        "coarse_profile_checksum":checksum(profile.capabilities_json)}
    row=db.get(GenesisBotanicalToolCertificate,item_id)
    if row is not None:
        if row.certificate!=cert or row.certificate_checksum!=checksum(cert):raise ValueError("Cannot silently recertify tool")
        return row
    row=GenesisBotanicalToolCertificate(item_id=item_id,certificate=cert,certificate_checksum=checksum(cert))
    db.add(row);db.flush();return row


def _action(db,cid,actor_id,individual_id,action_id,request):
    if not isinstance(action_id,str) or not 1<=len(action_id)<=128:raise ValueError("Bounded idempotency key required")
    old=db.get(GenesisPlantAction,(cid,action_id),populate_existing=True)
    if old:
        if (checksum(old.receipt)!=old.receipt_checksum or old.actor_id!=actor_id or old.individual_id!=individual_id or
                old.receipt["request"]!=request):raise ValueError("Action key reused with different arguments or corrupted receipt")
        return deepcopy(old.receipt)


def harvest(db,campaign_id,actor_id,individual_id,part_id,quantity,tool_instance_id,action_id):
    """One atomic transfer from an adult's finite part stock to the existing item ledger."""
    if type(quantity) is not int or quantity<=0:raise ValueError("Positive integer quantity required")
    sampler=context(db,campaign_id)
    request={"kind":"harvest","part_id":part_id,"quantity":quantity,"tool_instance_id":tool_instance_id}
    replay=_action(db,campaign_id,actor_id,individual_id,action_id,request)
    if replay is not None:return replay
    _fence(db,campaign_id)
    with db.begin_nested():
        old=_action(db,campaign_id,actor_id,individual_id,action_id,request)
        if old is not None:return old
        row=db.get(GenesisPlantIndividual,(campaign_id,individual_id),populate_existing=True)
        if row is None:raise ValueError("Individual not materialized")
        _validate_individual(row);_present(db,campaign_id,actor_id,row,sampler)
        from .lifecycle import sync,phase_available
        sync(db,campaign_id,row,sampler)
        query_environment(db,campaign_id,SurfacePoint(*row.baseline["point"]))
        community=db.get(GenesisVegetationCommunity,(campaign_id,row.community_id));_validate_community(community,sampler)
        _physical_current(db,campaign_id,community)
        if not row.state["alive"]:raise ValueError("Individual removed; no regrowth by revisit")
        sp=sampler.catalog.species[row.baseline["species_id"]]
        part=next((p for p in sp.parts() if p["id"]==part_id),None)
        if part is None or row.state["part_stock"].get(part_id,0)<quantity:raise ValueError("Insufficient mature part stock")
        clock=get_world_time(db,campaign_id)
        if not phase_available(row.baseline,row.state,part_id,clock.total_minutes(),sp):raise ValueError('Outside L1 maturity/phenology')
        season={"SPRING":"primavera","SUMMER":"verao","AUTUMN":"outono","WINTER":"inverno"}[current_season(db,campaign_id).value]
        period="manha" if 6<=clock.hour<12 else "tarde" if 12<=clock.hour<18 else "noite"
        if "resource_signature" in row.baseline:
            from .resources import available_now
            allowed,reason=available_now(db,campaign_id,sampler,row,part,clock)
            if not allowed:raise ValueError("Outside catalog availability: "+str(reason))
        elif season not in part["disponibilidade"]["estacoes"] or period not in part["disponibilidade"]["periodos_do_dia"]:
            raise ValueError("Outside the catalog seasonal/time window")
        proto=part["protocolo_campo_v7"]
        prof_id=next(v for k,v in proto.items() if k.startswith("profici") and k.endswith("principal_id"))
        skill=db.query(CharacterSkill).filter_by(character_id=actor_id,skill_id=prof_id).first()
        if skill is None or skill.mastery<proto["dificuldade_base_0_100"]:
            raise ValueError("Procedure proficiency unresolved or insufficient; no item or free XP")
        tool_context=validate_character_tool_use(db,actor_id,tool_instance_id,required_capability=ToolCapability.CUTTING)
        resource_profile=row.baseline.get("resource_profile")
        if resource_profile is not None and tool_context.accessibility.value=="STOWED":
            raise ValueError("Retrieve the stowed tool before harvesting")
        tool=db.get(ItemInstance,tool_instance_id);cert=db.get(GenesisBotanicalToolCertificate,tool.definition_id)
        from app.db.models.tool import ItemToolProfile
        coarse=db.get(ItemToolProfile,tool.definition_id)
        if (cert is None or checksum(cert.certificate)!=cert.certificate_checksum or
                cert.certificate["coarse_profile_checksum"]!=checksum(coarse.capabilities_json) or
                not set(proto["capacidades_necessarias_da_ferramenta"])<=set(cert.certificate["capabilities"])):
            raise ValueError("Named/coarse tool is not proof of fine botanical capabilities")
        item=db.get(ItemDefinition,part["item_id"])
        canonical_key=part["item_id"].lower().replace("-","_")
        calibration=getattr(sampler,"calibrations",{}).get(part_id)
        r1_part=resource_profile["parts"][part_id] if resource_profile else None
        if r1_part:
            from .resources import header
            authority=header(db,campaign_id,sampler)
            if authority is None or authority.signature!=row.baseline["resource_signature"]:raise ValueError("R1 authority mismatch")
        if sampler.config.vegetation_version==2 and calibration is None and r1_part is None:
            raise ValueError("Reviewed botanical mass/yield calibration required; zero mass is not authorized")
        mass=(r1_part["unit_mass_mg"]/row.baseline["inventory_mg_per_weight_unit"] if r1_part else
            calibration.unit_mass_mg/calibration.inventory_mg_per_weight_unit if calibration else 0)
        if r1_part is None and sampler.config.vegetation_version==2 and item is not None and item.base_weight!=mass:
            raise ValueError("Existing canonical item mass requires explicit migration; never overwrite legacy zero mass")
        if item is None:
            item=ItemDefinition(id=part["item_id"],key=canonical_key,name=part["item_nome"],type="MISC",instance_mode="STACKABLE",
                description="Material vegetal coletado; efeitos e consumo não confirmados.",base_weight=mass,base_value_bronze=None,
                stats_json='{}')
            db.add(item);db.flush()
        elif item.name!=part["item_nome"] or item.key!=canonical_key:raise ValueError("Canonical flora item collision")
        if r1_part:
            from .resources import consume
            if 'life' in row.state:
                from .lifecycle import harvest_state as consume
            previous_stock=deepcopy(row.state["part_stock"])
            state,exported_mass=consume(row.baseline,row.state,part_id,quantity,clock.total_minutes())
        else:
            state=deepcopy(row.state);state["part_stock"][part_id]-=quantity;state["revision"]+=1
            if not part["colheita_preserva_individuo"] or part["parte"]=="raiz":
                state["alive"]=False;state["part_stock"]={k:0 for k in state["part_stock"]}
        row.state=state;row.state_checksum=checksum(state)
        if 'life' in state and not state['alive']:
            from .lifecycle import record_death
            record_death(db,campaign_id,row,sampler)
            state=row.state
        instance=create_item_instance(db,item,quantity=quantity)
        if r1_part:
            instance.unit_weight_override=mass;instance.weight_authority="R1:"+row.baseline["resource_signature"]+":"+resource_profile["profile_checksum"]
            db.flush()
        move_item_instance(db,instance,location_type=ItemLocationType.CHARACTER,location_ref=actor_id)
        set_item_owner(db,instance,owner_type=ItemOwnerType.CHARACTER,owner_ref=actor_id)
        receipt={"action_id":action_id,"request":request,"individual_id":individual_id,"species_id":sp.id,
            "part_id":part_id,"item_id":part["item_id"],"item_instance_id":instance.id,"quantity":quantity,
            "stock_after":state["part_stock"],"individual_alive":state["alive"],"revision":state["revision"],
            "world_minute":clock.total_minutes(),"proficiency_id":prof_id,"tool_certificate_checksum":cert.certificate_checksum,
            "quality":"STANDARD","preservation":"unprocessed_perishable" if part["perecivel"] else "unprocessed",
            "arcane_effects":False,"automatic_price":None,"automatic_xp":0,"regrowth_scheduled":False}
        if calibration:
            receipt.update(unit_mass_mg=calibration.unit_mass_mg,calibration_checksum=checksum(calibration.model_dump()),
                measurement_evidence_ref=calibration.evidence_ref,inventory_mg_per_weight_unit=calibration.inventory_mg_per_weight_unit)
        if r1_part:
            receipt.update(resource_signature=row.baseline["resource_signature"],profile_checksum=resource_profile["profile_checksum"],
                unit_mass_mg=r1_part["unit_mass_mg"],exported_mass_mg=exported_mass,tissue_remaining_mg=state["tissue_remaining_mg"],
                stock_before=previous_stock,destructive=not state["alive"],maturity=row.baseline["maturity"],
                phenology=row.baseline["phenology"],mass_provenance="derived_gameplay_estimate_not_measurement",
                inventory_mg_per_weight_unit=row.baseline["inventory_mg_per_weight_unit"])
        if 'life' in state:receipt.update(life_signature=state['life']['signature'],maturity=state['life']['maturity'],recovery_enabled=state['alive'])
        _validate_individual(row)
        db.add(GenesisPlantAction(campaign_id=campaign_id,action_id=action_id,individual_id=individual_id,actor_id=actor_id,
            receipt=receipt,receipt_checksum=checksum(receipt)));db.flush()
        return deepcopy(receipt)


def remove_individual(db,campaign_id,actor_id,individual_id,tool_instance_id,action_id):
    """Finite destructive removal, no invented timber/item output from the flora catalog."""
    sampler=context(db,campaign_id)
    request={"kind":"remove","tool_instance_id":tool_instance_id}
    replay=_action(db,campaign_id,actor_id,individual_id,action_id,request)
    if replay is not None:return replay
    _fence(db,campaign_id)
    with db.begin_nested():
        old=_action(db,campaign_id,actor_id,individual_id,action_id,request)
        if old is not None:return old
        row=db.get(GenesisPlantIndividual,(campaign_id,individual_id),populate_existing=True)
        if row is None:raise ValueError("Individual not materialized")
        _validate_individual(row);_present(db,campaign_id,actor_id,row,sampler)
        from .lifecycle import sync
        sync(db,campaign_id,row,sampler)
        query_environment(db,campaign_id,SurfacePoint(*row.baseline["point"]))
        community=db.get(GenesisVegetationCommunity,(campaign_id,row.community_id));_validate_community(community,sampler)
        _physical_current(db,campaign_id,community)
        if not row.state["alive"]:raise ValueError("Individual already removed")
        if "resource_signature" in row.baseline:
            from .resources import header
            r1=header(db,campaign_id,sampler)
            if r1 is None or r1.signature!=row.baseline["resource_signature"]:raise ValueError("R1 authority mismatch")
        kind=sampler.catalog.species[row.baseline["species_id"]].kind
        removal_tool=validate_character_tool_use(db,actor_id,tool_instance_id,
            required_capability=ToolCapability.SAWING if kind=="arvore" else ToolCapability.CUTTING)
        if "resource_signature" in row.baseline and removal_tool.accessibility.value=="STOWED":
            raise ValueError("Retrieve the stowed tool before removal")
        state={**deepcopy(row.state),"alive":False,"part_stock":{k:0 for k in row.state["part_stock"]},"revision":row.state["revision"]+1}
        if "resource_signature" in row.baseline:
            state["discarded_mass_mg"]+=sum(state["tissue_remaining_mg"].values());state["tissue_remaining_mg"]={k:0 for k in state["tissue_remaining_mg"]}
            state["last_harvest_world_minute"]=get_world_time(db,campaign_id).total_minutes();state["last_removed_part"]="whole_individual"
        row.state=state;row.state_checksum=checksum(state)
        if 'life' in state:
            from .lifecycle import record_death
            record_death(db,campaign_id,row,sampler)
            state=row.state
        _validate_individual(row)
        receipt={"action_id":action_id,"request":request,"individual_id":individual_id,"individual_alive":False,
            "revision":state["revision"],"items_created":0,"regrowth_scheduled":False}
        db.add(GenesisPlantAction(campaign_id=campaign_id,action_id=action_id,individual_id=individual_id,actor_id=actor_id,
            receipt=receipt,receipt_checksum=checksum(receipt)));db.flush()
        return deepcopy(receipt)
