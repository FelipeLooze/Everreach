"""Finite founding history on fixed physical patches, independent of visits and render LOD.

No source here asserts a water body, soil chemistry, cave, anomaly or permanent flow.
W1 columns provide regional suitability, not an extra withdrawal from water stocks.
"""
from collections import Counter,OrderedDict
from copy import deepcopy
from .catalog import load_flora_catalog
from .config import VegetationConfig,TYPE_HEIGHT_CM
from ..formation_noise import noise,unit_direction
from ..formation_plan import cell_index
from ..sphere_topology import cell_at
from ..terrain.address import tile_at,level_for_spacing
from ..terrain.field import checksum
from ..water.config import check_climate_contract,WaterConfigC3R155


def eligibility(species,environment,water):
    """Explicit tri-state filters. Missing required evidence never means suitable."""
    if species.magic=="excepcional":
        return "pending",["exact_authorized_persisted_anomaly_source:"+str(species.anomaly)]
    if species.extreme_json:
        return "pending",["localized_geometry_energy_substrate_and_microhabitat_evidence"]
    if species.kind in ("alga","junco","consorcio_simbiotico"):
        return "pending",["confirmed_local_water_column_or_specialized_energy_source"]
    f=environment["logical_facts"]
    if not f["terreno.evidencia_superficie_continental"]:
        return "incompatible",["not_open_land"]
    hs=set(environment["flora_contract"]["eligible_habitat_ids"])
    if not hs.intersection(species.habitats):return "incompatible",["no_eligible_E1_habitat"]
    keys=((species.temperature,"clima.temperatura_media_anual_c"),
          (species.rain,"clima.precipitacao_anual_mm"))
    missing=[]
    for limits,key in keys:
        value=f.get(key)
        if limits is None or value is None:missing.append(key+"_or_species_reference")
        elif not limits[0]<=value<=limits[1]:return "incompatible",[key]
    ratio=f.get("clima.indice_aridez")
    if ratio is None:missing.append("P_over_PET")
    elif species.aridity is not None and not species.aridity[0]<=ratio<=species.aridity[1]:
        return "incompatible",["species_aridity_reference"]
    if not environment["physical_inputs"].get("substrates"):missing.append("JR1_surface_substrate")
    if water.get("macro_marine") is not False:missing.append("terrestrial_W1_column")
    if water.get("ET_mm") is None:missing.append("regional_soil_water_cycle")
    elif water["ET_mm"]<=0:return "incompatible",["no_modeled_accessible_water"]
    seasons=environment["physical_inputs"].get("C3_seasons")
    if not seasons:missing.append("seasonal_surface_energy")
    elif max(s["temperature_centi_c"] for s in seasons)<=0 and species.kind not in ("liquen","musgo"):
        return "incompatible",["no_modeled_thaw_season"]
    if missing:return "pending",missing
    # Versioned functional limits, deliberately conservative; not new source measurements.
    p=f["clima.precipitacao_anual_mm"];t=f["clima.temperatura_media_anual_c"]
    if species.kind=="arvore" and (p<160 or ratio<0.15 or t<-8):
        return "incompatible",["Vg1_tree_water_and_temperature_limit"]
    if species.kind=="samambaia" and ratio<0.35:return "incompatible",["Vg1_fern_water_limit"]
    if species.kind=="trepadeira":return "pending",["localized_established_support"]
    if species.kind=="fungo":return "pending",["localized_detrital_energy"]
    return "eligible",[]


def physiognomy(populations,cover,temp):
    if not populations:return "barren"
    weights=Counter()
    for p in populations:weights[p["kind"]]+=p["cover_ppm"]
    trees=weights["arvore"]
    if trees>=500000:return "dense_forest"
    if trees>=250000:return "open_forest"
    if trees>=100000:return "woodland"
    if temp<-5:return "polar_alpine_cover"
    if trees>=30000 and weights["graminea"]>50000:return "savanna_mosaic"
    if weights["arbusto"]>cover//3:return "shrubland"
    if weights["liquen"]+weights["musgo"]>cover//2:return "cryptogam_cover"
    if cover<120000:return "sparse_desert_vegetation"
    if cover<350000:return "steppe"
    return "grass_forb_field"


class VegetationSampler:
    def __init__(self,environment,water,config=None):
        if config is not None and config.vegetation_version!=1 and type(self) is VegetationSampler:
            raise ValueError("Use the explicit versioned factory for Vg2")
        check_climate_contract(water.config,environment.climate.config)
        if not isinstance(water.config,WaterConfigC3R155) or water.climate_signature!=environment.climate.signature:
            raise ValueError("Vg1 requires actual W1-C3 R1-55 forcing, never C2 relabelling")
        if water.hydrology.signature!=environment.h1.signature:
            raise ValueError("Vg1 hydrology authority mismatch")
        self.environment,self.water=environment,water
        self.config=config or VegetationConfig()
        self.catalog=load_flora_catalog()
        self.radius=environment.regional.sites.radius
        self.seed=environment.regional.terrain.plan.source.seed
        self.level=level_for_spacing(self.radius,self.config.patch_spacing_m,1)
        self.descriptor={"kind":"vegetation_vg1","config":self.config.model_dump(),"flora_sha256":self.catalog.source_hash,
            "E1_signature":environment.signature,"E1_descriptor_checksum":checksum(environment.descriptor),
            "water_signature":water.signature,"water_checksum":checksum(water.to_dict()),
            "physical_patch_level":self.level,"radius_m":self.radius,"world_seed":self.seed,
            "structure_policy":"legacy_type_height_v1", "water_scope":"macro_suitability_not_local_depth_or_consumption",
            "surface_policy":"exposed_terrestrial_founder_microsites_v1_not_measured_soil_chemistry",
            "stock_policy":"only_nonnull_catalog_stock_no_automatic_regrowth"}
        self.signature=checksum(self.descriptor)[:24]
        self.cache=OrderedDict()

    def address(self,point):
        a=tile_at(point,self.level)
        return a,"vg1:"+checksum([self.signature,[a.face,a.level,a.x,a.y]])[:32]

    def _field(self,point,wavelength,domain):
        return noise(self.seed,unit_direction(point),self.radius,wavelength,"Vg1/"+domain)

    def water_facts(self,point):
        w=self.water;n=cell_index(cell_at(point,w.hydrology.config.level));area=w.hydrology.cell_area_m2[n]
        return {"node":n,"macro_marine":w.hydrology.drainage.marine[n],
            "ET_mm":sum(p["fluxes"]["evapotranspiration"][n] for p in w.solution.periods)/area,
            "soil_mm_by_period":[p["stores"]["soil"][n]/area for p in w.solution.periods],
            "local_runoff_mm":sum(p["fluxes"]["local_runoff"][n] for p in w.solution.periods)/area,
            "water_signature":w.signature,"scope":"regional_model_not_point_stock"}

    def sample(self,point):
        a,identifier=self.address(point)
        if identifier in self.cache:return deepcopy(self.cache[identifier])
        # Always derive from the same physical center; a render tile never chooses history.
        center=a.point(1,1,2);e=self.environment.sample(center);w=self.water_facts(center);f=e["logical_facts"]
        candidates=sorted({s for h in e["flora_contract"]["eligible_habitat_ids"] for s in self.catalog.by_habitat.get(h,())})
        accepted=[];states=Counter();reasons=Counter()
        for sid in candidates:
            sp=self.catalog.species[sid];state,why=eligibility(sp,e,w)
            states[state]+=1;reasons.update(why)
            if state!="eligible":continue
            # Smooth geographic ranges; rarity is an isolation threshold, never a visit roll.
            broad=self._field(center,self.config.broad_range_m,"range/"+sid)
            if broad < -7000+sp.rarity*95:continue
            rank=self._field(center,128000,"composition/"+sid)
            if self.config.policy=="exploration_mosaic_v1":
                rank=(rank+3*self._field(center,self.config.mosaic_m,"mosaic/"+sid))//4
            accepted.append((rank,sid))
        accepted.sort(reverse=True)
        accepted=accepted[:self.config.species_budget]
        ratio=f.get("clima.indice_aridez");temp=f["clima.temperatura_media_anual_c"]
        ratio=0 if ratio is None else max(0,ratio)
        ecological_cover=int(min(920000,900000*ratio/(0.25+ratio)))
        if temp<-5:ecological_cover=ecological_cover*max(2,int(temp+30))//30
        if not accepted:ecological_cover=0
        slope=f["terreno.declividade_graus"]
        cover=max(0,ecological_cover*(100-min(85,int(slope)))//100)
        if self.config.policy=="exploration_mosaic_v1":
            # Deliberate game direction: vary the occupied fraction, never create water,
            # accept an incompatible species, or exceed the ecological cover ceiling.
            mosaic=self._field(center,self.config.mosaic_m,"clearings")
            cover=cover*(750000+25*mosaic)//1000000
        populations=[]
        weights=[max(1,10000+rank) for rank,_ in accepted];total=sum(weights) or 1
        if self.config.policy=="exploration_mosaic_v1" and ratio>=0.5 and temp>-8:
            trees=[i for i,(_,sid) in enumerate(accepted) if self.catalog.species[sid].kind=="arvore"]
            rest=[i for i in range(len(accepted)) if i not in trees]
            if trees and rest:
                # Distinct canopy/understory architecture from actual founder species.
                # A smooth field allows clearings, groves and dense canopy in wet climates.
                canopy=max(200000,min(950000,int(350000+350000*min(ratio,1.5))+20*self._field(center,self.config.mosaic_m*2,"canopy")))
                tw=sum(weights[i] for i in trees);rw=sum(weights[i] for i in rest)
                weights=[max(1,weights[i]*(canopy if i in trees else 1000000-canopy)//(tw if i in trees else rw)) for i in range(len(accepted))]
                total=sum(weights)
        assigned=0
        for i,((rank,sid),weight) in enumerate(zip(accepted,weights)):
            sp=self.catalog.species[sid];height=sp.height_cm or TYPE_HEIGHT_CM[sp.kind]
            mature=height[0]+(height[1]-height[0])*(10000+self._field(center,32000,"height/"+sid))//20000
            share=cover-assigned if i==len(accepted)-1 else cover*weight//total;assigned+=share
            # Fixed, finite population of representative organisms/colonies per physical area.
            # Cube-sphere cell area integrated by exact solid angle, not chart rectangle area.
            area=self._patch_area(a)
            footprint=max(1,(mature/100)**2//4) if sp.kind=="arvore" else 1
            count=max(1,int(area*share/1000000/footprint)) if share else 0
            if not count:continue
            populations.append({"population_id":"vgp:"+checksum([identifier,sid])[:32],"species_id":sid,
                "kind":sp.kind,"height_cm":mature,"height_source":"catalog" if sp.height_cm else "Vg1_game_type_architecture",
                "cover_ppm":share,"founder_count":count,"origin":self.config.founding,
                "maturity":"adult_founder_history","rarity_index_not_spawn_percent":sp.rarity})
        populations.sort(key=lambda p:(-p["cover_ppm"],p["species_id"]))
        result={"kind":"established_vegetation_patch_vg1","authority_signature":self.signature,"community_id":identifier,
            "physical_address":[a.face,a.level,a.x,a.y],"point":list(center.xyz),"patch_area_m2":self._patch_area(a),
            "E1_probe_id":e["probe_id"],"E1_primary_potential":e["primary_potential"],
            "source_evidence":{"E1":self.environment.signature,"JR1":e["physical_inputs"]["JR1_checksum"],
                "C3":self.environment.climate.signature,"water":w,"temperature_c":temp,"rain_mm":f["clima.precipitacao_anual_mm"],"P_over_PET":f.get("clima.indice_aridez")},
            "candidate_counts":dict(states),"pending_or_incompatible_reasons":dict(reasons),
            "founding_rule":self.config.founding,"populations":populations,"established":bool(populations),
            "dominant_species":populations[0]["species_id"] if populations else None,
            "secondary_species":[p["species_id"] for p in populations[1:]],"cover_ppm":sum(p["cover_ppm"] for p in populations),
            "clearing_ppm":1000000-sum(p["cover_ppm"] for p in populations),
            "physiognomy":physiognomy(populations,cover,temp),
            "density_per_ha":int(sum(p["founder_count"] for p in populations)*10000/self._patch_area(a)),
            "strata_cover_ppm":dict(Counter({k:sum(p["cover_ppm"] for p in populations if ("canopy" if p["height_cm"]>=500 else "shrub" if p["height_cm"]>=100 else "ground")==k) for k in ("canopy","shrub","ground")})),
            "direction_policy":self.config.policy,"ecological_cover_ceiling_ppm":ecological_cover,
            "individuals_materialized":0,"future_ecology":{"growth":"explicit_future_event_only","reproduction":"requires_viable_propagule_and_elapsed_world_time","automatic_recovery":False},
            "public_map_export":False,"persisted":False}
        self.cache[identifier]=result
        while len(self.cache)>128:self.cache.popitem(last=False)
        return deepcopy(result)

    def _patch_area(self,a):
        from ..sphere_area import _triangle_area
        p,q,r,s=(a.point(x,y,1).xyz for x,y in ((0,0),(1,0),(1,1),(0,1)))
        return max(1,int((_triangle_area(p,q,r)+_triangle_area(p,r,s))*self.radius**2))
