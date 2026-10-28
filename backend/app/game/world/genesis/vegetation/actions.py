"""Structured player actions inside the existing checkpoint/response pipeline.

Narration never grants items. No arbitrary coordinate or ecology override is accepted.
"""
from copy import deepcopy
from dataclasses import asdict
from math import isqrt
from app.db.models.character import Character
from app.db.models.world_spatial import LocationSpatialAnchor
from app.db.models.world_vegetation import GenesisPlantIndividual,GenesisPlantAction
from app.game.time.clock import get_world_time,current_season,advance_world_time
from ..sphere_topology import SurfacePoint
from ..sphere_metric import distance_m
from ..terrain.address import chart,point_on_face
from ..terrain.field import checksum
from . import service
from .resources import header,ResourceConfigR1


def inspect(db,cid,actor_id,iid,*,_sampler=None,_physical_checked=False):
    sampler=_sampler if _sampler is not None else service.context(db,cid)
    observation=service.observe_individual(db,cid,actor_id,iid,_sampler=sampler,_physical_checked=_physical_checked)
    row=db.get(GenesisPlantIndividual,(cid,iid));profile=row.baseline.get("resource_profile")
    if profile is None:return {**observation,"parts":[],"resource_state":"legacy_unmigrated"}
    clock=get_world_time(db,cid)
    season={"SPRING":"primavera","SUMMER":"verao","AUTUMN":"outono","WINTER":"inverno"}[current_season(db,cid).value]
    period="manha" if 6<=clock.hour<12 else "tarde" if 12<=clock.hour<18 else "noite"
    sp=sampler.catalog.species[row.baseline["species_id"]];parts=[]
    for p in sp.parts():
        record=profile["parts"][p["id"]];remaining=row.state["part_stock"][p["id"]]
        from .resources import available_now
        allowed,reason=available_now(db,cid,sampler,row,p,clock)
        from .lifecycle import phase_available,PARTIAL
        if not phase_available(row.baseline,row.state,p['id'],clock.total_minutes(),sp):allowed=False;reason='outside_L1_maturity_or_phenology'
        available=row.state["alive"] and remaining>0 and allowed
        if not row.state["alive"]:reason="individual_removed"
        elif record["state"]!="usable":reason=record.get("reason")
        elif remaining==0:reason='depleted_or_waiting_for_L1_growth' if 'life' in row.state else "not_mature_in_founder_phenology_or_depleted"
        parts.append({"part_id":p["id"],"part":p["parte"],"item_id":p["item_id"] if observation["identified"] else None,
            "remaining":remaining,"initial":row.baseline["initial_part_stock"][p["id"]],"available_now":bool(available),
            **({'maximum':record['max_units']} if 'life' in row.state else {}),
            "unit_mass_mg":record.get("unit_mass_mg"),"per_action_max":record.get("per_action_max"),
            "destructive":(record['part'] not in PARTIAL if 'life' in row.state else not record.get("preserves_individual",False)),"state":record["state"],"reason":reason})
    return {**observation,"parts":parts,"resource_signature":row.baseline["resource_signature"],"phenology":'seasonal_L1' if 'life' in row.state else row.baseline["phenology"]}


def encounter(db,cid,actor):
    sampler=service.context(db,cid);anchor=db.get(LocationSpatialAnchor,actor.location_id)
    if anchor is None or anchor.campaign_id!=cid:raise ValueError("Player location needs a physical anchor")
    point=SurfacePoint(*anchor.point);candidates=[];parents={}
    from ..geology.regional.experiment import window_point
    patches={sampler.address(q)[1]:q for q in (window_point(point,x,y,sampler.radius) for x in (-5,0,5) for y in (-5,0,5))}
    for query_point in patches.values():
        community=service.materialize_community(db,cid,query_point,_sampler=sampler)
        parents[community.community_id]=community
        candidates.extend(_nearby_slots(sampler,community,point))
    result=[];seen=set()
    for distance,sid,slot,query_point in sorted(candidates,key=lambda r:r[:3]):
        if sid in seen:continue
        try:row=service.materialize_individual(db,cid,query_point,sid,slot,_sampler=sampler,_community=parents[sampler.address(query_point)[1]])
        except ValueError as exc:
            if "microsite unsupported" in str(exc):continue
            raise
        from .lifecycle import current_occupant
        row=current_occupant(db,cid,row,sampler)
        seen.add(sid);result.append({**inspect(db,cid,actor.id,row.individual_id,_sampler=sampler,_physical_checked=True),"distance_m":round(distance,2)})
        if len(result)>=8:break
    return result


def _nearby_slots(sampler,community,point,*,radius_m=5):
    a,_=sampler.address(SurfacePoint(*community.baseline["point"]));_,u,v,d=chart(point,a.face);candidates=[]
    # Invert the fixed permutation of finite slots. At most 9 candidates per population.
    for pop in community.baseline["populations"]:
        grid=1
        while grid*grid<pop["founder_count"]:grid*=2
        salt=int(checksum([pop["population_id"],"position"])[:16],16)
        modulus=grid*grid;mult=2*(salt//modulus)+1
        inverse=pow(mult,-1,modulus) if modulus>1 else 0
        ix=u*(2**a.level)*grid//d-a.x*grid;iy=v*(2**a.level)*grid//d-a.y*grid
        for x in range(max(0,ix-1),min(grid,ix+2)):
            for y in range(max(0,iy-1),min(grid,iy+2)):
                slot=((y*grid+x-salt)*inverse)%modulus if modulus>1 else 0
                if slot>=pop["founder_count"]:continue
                position=point_on_face(a.face,2*a.x*grid+2*x+1,2*a.y*grid+2*y+1,2**(a.level+1)*grid)
                distance=distance_m(sampler.environment.regional.terrain.plan.source.config,point,position)
                if distance<=radius_m:candidates.append((distance,pop["species_id"],slot,SurfacePoint(*community.baseline["point"])))
    return candidates


def resolve_plant_action(db,cid,actor_id,request,action_key):
    from app.game.engine import ActionResult,CharacterDeadError,WorldNotStartedError
    actor=db.get(Character,actor_id)
    if actor is None or actor.campaign_id!=cid:raise ValueError("Unknown character in campaign")
    if actor.status!="ALIVE" or actor.hp_current<=0:raise CharacterDeadError("A living character is required")
    if actor.location_id is None:raise WorldNotStartedError("Start the experimental world first")
    from app.game.combat.encounters import get_active_encounter_for_actor
    from app.core.enums import CombatActorType
    if get_active_encounter_for_actor(db,CombatActorType.CHARACTER,actor_id):raise ValueError("Plant collection is unavailable during active combat")
    sampler=service.context(db,cid);authority=header(db,cid,sampler)
    if authority is None:raise ValueError("Activate experimental R1 resources explicitly")
    if not 1<=len(action_key)<=128:raise ValueError("Plant action key must have 1–128 characters")
    old=db.get(GenesisPlantAction,(cid,action_key));mutation=request.kind in ("harvest","remove")
    if request.kind=="harvest":
        result=service.harvest(db,cid,actor_id,request.individual_id,request.part_id,request.quantity,request.tool_instance_id,action_key)
        summary=f"Coletadas {result['quantity']} unidade(s) de {result['part_id']}; {result.get('exported_mass_mg',0)} mg transferidos ao inventário."
    elif request.kind=="remove":
        result=service.remove_individual(db,cid,actor_id,request.individual_id,request.tool_instance_id,action_key)
        summary="Indivíduo removido. Nenhum item de madeira ou outro produto não definido foi criado."
    elif request.kind=="observe":result=inspect(db,cid,actor_id,request.individual_id);summary="Partes e estado do indivíduo observados."
    else:result={"individuals":encounter(db,cid,actor)};summary="Vegetação próxima observada; recursos permanecem no mundo."
    if mutation and old is None:
        minutes=ResourceConfigR1.model_validate(authority.descriptor["config"]).collect_minutes
        advance_world_time(db,cid,minutes)
    if mutation:
        from app.game.items.encumbrance import get_character_encumbrance
        result={**result,"encumbrance":asdict(get_character_encumbrance(db,actor_id))}
    response=ActionResult(narrative=summary,narrator_unavailable=False,mechanical_summary=summary,intent_type="PLANT_"+request.kind.upper())
    response.plant_result=result
    return response
