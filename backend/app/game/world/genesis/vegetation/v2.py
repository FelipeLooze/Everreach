"""Vg2: blended regional species cohorts; canopy gaps retain suitable ground cover.

Vg1's formulae and output descriptors remain untouched. No climate/water feedback.
"""
from collections import Counter,OrderedDict
from copy import deepcopy
from itertools import product
from .field import VegetationSampler,eligibility,physiognomy
from .config import VegetationConfigV2,TYPE_HEIGHT_CM
from ..formation_noise import unit_direction,UNIT
from ..sphere_topology import SurfacePoint
from ..terrain.field import checksum

TREE="tree";GROUND="ground"
_UNRESOLVED_MICROENVIRONMENT = object()


class VegetationSamplerV2(VegetationSampler):
    def __init__(self,environment,water,config=None):
        super().__init__(environment,water,config or VegetationConfigV2())
        self.descriptor={**self.descriptor,"kind":"vegetation_vg2","config":self.config.model_dump(mode="json"),
            "composition_policy":"spherical_blended_regional_guild_cohorts_r1",
            "coverage_policy":"ecological_base_plus_water_supported_infill_r1",
            "stock_policy":"reviewed_per_part_mass_and_yield_v1_no_default_stock"}
        self.signature=checksum(self.descriptor)[:24];self.cohorts=OrderedDict()
        self.calibrations={}
        pools={}
        if len({c.inventory_mg_per_weight_unit for c in self.config.resource_calibrations})>1:
            raise ValueError("A world requires one explicit inventory weight conversion")
        for c in self.config.resource_calibrations:
            sp=self.catalog.species.get(c.species_id)
            if sp is None or sp.kind!=c.organism_type:raise ValueError("Calibration species/type mismatch")
            part=next((p for p in sp.parts() if p["id"]==c.part_id),None)
            if part is None or c.part_id in self.calibrations:raise ValueError("Unknown/duplicate calibrated part")
            if type(part.get("quantidade_max")) is int and c.max_mature_units>part["quantidade_max"]:
                raise ValueError("Calibration exceeds canonical part maximum")
            self.calibrations[c.part_id]=c
            key=(c.species_id,c.tissue_pool_id);budget=c.available_tissue_mass_mg*c.removable_fraction_ppm//1000000
            if key in pools and pools[key][0]!=budget:raise ValueError("Conflicting shared tissue pool budgets")
            used=pools.get(key,(budget,0))[1]+c.max_mature_units*c.unit_mass_mg
            if used>budget:raise ValueError("Parts double allocate a shared tissue pool")
            pools[key]=(budget,used)

    def address(self,point):
        a,_=super().address(point)
        return a,"vg2:"+checksum([self.signature,[a.face,a.level,a.x,a.y]])[:32]

    def _anchors(self,point):
        # Ambient Cartesian lattice with C1 interpolation. No cube-chart boundary.
        axes=[divmod(v*self.radius,self.config.community_spacing_m*UNIT) for v in unit_direction(point)]
        for bits in product((0,1),repeat=3):
            key=tuple(q+b for (q,_),b in zip(axes,bits));weight=1000000
            for (_,r),b in zip(axes,bits):
                den=self.config.community_spacing_m*UNIT;t=r*1000000//den
                t=t*t*(3000000-2*t)//10**12
                weight=weight*(t if b else 1000000-t)//1000000
            if weight:yield key,weight

    def _cohort(self,key,habitat):
        cache_key=(key,habitat)
        if cache_key in self.cohorts:return self.cohorts[cache_key]
        # Potential regional pool only; every established population is filtered locally.
        candidates=[]
        for sid in self.catalog.by_habitat.get(habitat,()):
            s=self.catalog.species[sid]
            if s.magic=="excepcional" or s.extreme_json or s.kind in ("fungo","trepadeira","junco","alga","consorcio_simbiotico"):continue
            score=int(checksum([self.seed,"Vg2_cohort",key,habitat,sid])[:12],16)
            candidates.append((score,sid))
        result={}
        for guild in (TREE,GROUND):
            pool=sorted((r for r in candidates if (self.catalog.species[r[1]].kind=="arvore")== (guild==TREE)),reverse=True)[:6]
            for i,(_,sid) in enumerate(pool):
                # Strong regional leaders, progressively rarer secondary associates.
                result[sid]=(guild,(520000,180000,120000,80000,60000,40000)[i])
        self.cohorts[cache_key]=result
        while len(self.cohorts)>256:self.cohorts.popitem(last=False)
        return result

    def sample(self,point,*,microenvironment=_UNRESOLVED_MICROENVIRONMENT):
        if microenvironment is _UNRESOLVED_MICROENVIRONMENT:
            if self.config.policy == "regional_canopy_wgs2_canonical_v1":
                raise ValueError("WGS2.3.1 sampling requires an explicit canonical microenvironment resolution")
            microenvironment = None
        a,identifier=self.address(point)
        if identifier in self.cache:
            cached=self.cache[identifier]
            if ("microenvironment_context" not in cached
                    or cached.get("microenvironment_context")==microenvironment):
                return deepcopy(cached)
        center=a.point(1,1,2);e=self.environment.sample(center)
        regional_aridity=e["logical_facts"].get("clima.indice_aridez")
        if microenvironment is not None:
            if self.config.policy not in ("regional_canopy_wgs2_microhabitat_v1", "regional_canopy_wgs2_canonical_v1"):
                raise ValueError("Local WGS2 microhabitats require the explicit Vg2 policy")
            from .microhabitat import apply_to_environment
            e=apply_to_environment(e,microenvironment)
        w=self.water_facts(center);f=e["logical_facts"]
        habitats=e["flora_contract"]["eligible_habitat_ids"];scores=Counter();states=Counter();reasons=Counter()
        for key,weight in self._anchors(center):
            for h in habitats:
                for sid,(_,abundance) in self._cohort(key,h).items():scores[sid]+=weight*abundance//1000000
        accepted=[]
        for sid,score in sorted(scores.items()):
            s=self.catalog.species[sid];state,why=eligibility(s,e,w);states[state]+=1;reasons.update(why)
            if state!="eligible":continue
            if self._field(center,self.config.broad_range_m,"range/"+sid)<-7000+s.rarity*95:continue
            accepted.append((score,sid))
        # Preserve viable sparse sites even when all interpolated regional pools miss them.
        if not accepted:
            ids=sorted({sid for h in habitats for sid in self.catalog.by_habitat.get(h,())})
            for sid in ids:
                s=self.catalog.species[sid]
                if eligibility(s,e,w)[0]=="eligible" and self._field(center,self.config.broad_range_m,"range/"+sid)>=-7000+s.rarity*95:
                    accepted.append((max(1,10000+self._field(center,128000,"composition/"+sid)),sid))
        accepted.sort(reverse=True);accepted=accepted[:self.config.species_budget]
        ratio=f.get("clima.indice_aridez");temp=f["clima.temperatura_media_anual_c"];ratio=max(0,ratio or 0)
        ceiling=int(min(920000,900000*ratio/(0.25+ratio)))
        if temp<-5:ceiling=ceiling*max(2,int(temp+30))//30
        if not accepted:ceiling=0
        base=max(0,ceiling*(100-min(85,int(f["terreno.declividade_graus"])))//100)
        # Diversity does not impose bare ground. Infill only uses existing headroom
        # where the W1 regional soil cycle and C3 water/energy support it.
        wet_support=ratio>=0.5 and w["ET_mm"]>0 and max(w["soil_mm_by_period"],default=0)>0
        infill=(ceiling-base)*max(0,self._field(center,24000,"Vg2/infill"))//10000 if wet_support else 0
        cover=base+infill
        trees=[i for i,(_,sid) in enumerate(accepted) if self.catalog.species[sid].kind=="arvore"]
        rest=[i for i in range(len(accepted)) if i not in trees]
        weights=[max(1,r) for r,_ in accepted]
        if trees and rest:
            structure=self._field(center,self.config.structure_wavelength_m,"Vg2/structure")
            gap=self._field(center,8000,"Vg2/canopy_gaps")
            canopy=max(20000,min(950000,int(250000+400000*min(ratio,1.5))+35*structure+3*gap))
            if ratio<0.5:canopy=min(canopy,int(400000*ratio))
            tw=sum(weights[i] for i in trees);rw=sum(weights[i] for i in rest)
            weights=[max(1,weights[i]*(canopy if i in trees else 1000000-canopy)//(tw if i in trees else rw)) for i in range(len(accepted))]
        total=sum(weights) or 1;assigned=0;pops=[];area=self._patch_area(a)
        for i,((_,sid),weight) in enumerate(zip(accepted,weights)):
            s=self.catalog.species[sid];heights=s.height_cm or TYPE_HEIGHT_CM[s.kind]
            height=heights[0]+(heights[1]-heights[0])*(10000+self._field(center,32000,"height/"+sid))//20000
            share=cover-assigned if i==len(accepted)-1 else cover*weight//total;assigned+=share
            if not share:continue
            footprint=max(1,height*height//40000) if s.kind=="arvore" else 1
            count=max(1,area*share//1000000//footprint)
            pops.append({"population_id":"vgp:"+checksum([identifier,sid])[:32],"species_id":sid,"kind":s.kind,
                "height_cm":height,"height_source":"catalog" if s.height_cm else "Vg1_game_type_architecture",
                "cover_ppm":share,"founder_count":count,"origin":self.config.founding,"maturity":"adult_founder_history",
                "rarity_index_not_spawn_percent":s.rarity})
        pops.sort(key=lambda p:(-p["cover_ppm"],p["species_id"]))
        strata={k:sum(p["cover_ppm"] for p in pops if ("canopy" if p["height_cm"]>=500 else "shrub" if p["height_cm"]>=100 else "ground")==k) for k in ("canopy","shrub","ground")}
        result={"kind":"established_vegetation_patch_vg2","authority_signature":self.signature,"community_id":identifier,
            "physical_address":[a.face,a.level,a.x,a.y],"point":list(center.xyz),"patch_area_m2":area,
            "E1_probe_id":e["probe_id"],"E1_primary_potential":e["primary_potential"],
            "source_evidence":{"E1":self.environment.signature,"JR1":e["physical_inputs"]["JR1_checksum"],
                "C3":self.environment.climate.signature,"water":w,"temperature_c":temp,"rain_mm":f["clima.precipitacao_anual_mm"],
                "P_over_PET":f.get("clima.indice_aridez"),"regional_P_over_PET":regional_aridity},
            "candidate_counts":dict(states),"pending_or_incompatible_reasons":dict(reasons),"founding_rule":self.config.founding,
            "populations":pops,"established":bool(pops),"dominant_species":pops[0]["species_id"] if pops else None,
            "secondary_species":[p["species_id"] for p in pops[1:]],"cover_ppm":cover,"clearing_ppm":1000000-cover,
            "physiognomy":physiognomy(pops,cover,temp),"density_per_ha":sum(p["founder_count"] for p in pops)*10000//area,
            "strata_cover_ppm":strata,"direction_policy":self.config.policy,"ecological_cover_ceiling_ppm":ceiling,
            "ecological_base_cover_ppm":base,"water_supported_infill_ppm":infill,
            "composition_scope":"blended_regional_cohorts_not_biome_replacement",
            "individuals_materialized":0,"future_ecology":{"growth":"explicit_future_event_only","reproduction":"requires_viable_propagule_and_elapsed_world_time","automatic_recovery":False},
            "public_map_export":False,"persisted":False}
        if self.config.policy in ("regional_canopy_wgs2_microhabitat_v1", "regional_canopy_wgs2_canonical_v1"):
            result["microenvironment_context"]=deepcopy(microenvironment)
            if self.config.policy == "regional_canopy_wgs2_canonical_v1":
                result["local_environment_signature"]=checksum({"version":"WGS2_LOCAL_ENVIRONMENT_R1",
                    "regional":self.environment.signature, "E1_probe_id":e["probe_id"],
                    "microenvironment":microenvironment})
            else:
                result["local_environment_signature"]=checksum({"regional":self.environment.signature,
                    "microenvironment":microenvironment.get("contract_signature") if microenvironment else None})
        self.cache[identifier]=result
        while len(self.cache)>128:self.cache.popitem(last=False)
        return deepcopy(result)
