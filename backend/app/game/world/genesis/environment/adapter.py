"""Adapt real C2/T1/JR1 fields. Unknown physical evidence stays unknown."""
from bisect import bisect_left
from collections import OrderedDict
from copy import deepcopy
from .classifier import NaturalClassifier,FEATURE_GUARDS,CONFIRMATION_GUARDS
from .config import EnvironmentConfig,source_climate_version
from ..terrain.field import checksum
from ..terrain.geometry import surface_geometry
from ..climate.query import sample_climate
from ..climate.geometry import interpolate,stencil
from ..sphere_topology import cell_at
from ..formation_plan import cell_index

# Frozen integer tangents at integer degrees; interpolation is an E1 slope proxy.
TANGENTS=(0,17455,34921,52408,69927,87489,105104,122785,140541,158384,176327,194380,212557,230868,249328,267949,286745,305731,324920,344328,363970,383864,404026,424475,445229,466308,487733,509525,531709,554309,577350,600861,624869,649408,674509,700208,726543,753554,781286,809784,839100,869287,900404,932515,965689,1000000,1035530,1072369,1110613,1150368,1191754,1234897,1279942,1327045,1376382,1428148,1482561,1539865,1600335,1664279,1732051,1804048,1880726,1962611,2050304,2144507,2246037,2355852,2475087,2605089,2747477,2904211,3077684,3270853,3487414,3732051,4010781,4331476,4704630,5144554,5671282,6313752,7115370,8144346,9514364,11430052,14300666,19081137,28636253,57289962)


def slope_centi_degrees(ppm):
    i=bisect_left(TANGENTS,ppm)
    if i==0:return 0
    if i>=len(TANGENTS):return 9000  # do not understate slopes beyond the 89-degree references
    return (i-1)*100+(ppm-TANGENTS[i-1])*100//(TANGENTS[i]-TANGENTS[i-1])


class EnvironmentSampler:
    def __init__(self,regional,h1,climate,config=None):
        expected_climate=source_climate_version(config or EnvironmentConfig())
        if (climate.config.climate_version!=expected_climate or climate.source_signature!=regional.terrain.plan.source.signature or
                climate.hydrology_signature!=h1.signature or h1.source_signature!=climate.source_signature or
                h1.radius_m!=regional.sites.radius or climate.radius_m!=regional.sites.radius or
                climate.sea_level_m!=regional.terrain.plan.source.config.sea_level_m):
            raise ValueError(f"E1 requires pinned V4/T1/C{expected_climate}/H1/J1/JR1; no legacy conversion")
        self.regional,self.h1,self.climate=regional,h1,climate
        self.classifier=NaturalClassifier(config)
        self.config=self.classifier.config
        self.descriptor={"kind":"environment_e1","environment_version":1,"taxonomy":"EV-ECO-1.1.1",
            "catalog_hashes":self.classifier.catalog["hashes"],"config":self.config.model_dump(),
            "jr1_signature":regional.signature,"jr1_descriptor":regional.descriptor,
            "climate_signature":climate.signature,"climate_checksum":checksum(climate.to_dict()),
            "hydrology_signature":h1.signature,"hydrology_checksum":checksum(h1.to_dict()),
            "hydrology_scope":"potential_drainage_not_permanent_water",
            "cryosphere_scope":"potential_freezing_and_snowfall_not_actual_ice",
            "ocean_scope":"V4_H1_reference_not_a_confirmed_local_water_column"}
        self.signature=checksum(self.descriptor)[:24]
        self.cache=OrderedDict()

    def sample(self,point):
        key=tuple(point.xyz)
        if key in self.cache:
            self.cache.move_to_end(key)
            return deepcopy(self.cache[key])
        terrain=surface_geometry(self.regional.terrain,point,8)
        climate=sample_climate(self.climate,point,_terrain_height=terrain["height_mm"]//1000)
        formation=self.regional.formation(point)
        parent=self.regional.macro.unit_at(point)
        facts={e["campo_canonico_proposto"]:None for r in self.classifier.catalog["rules"].values()
            for e in r["evidencias_fisicas_obrigatorias_all"]}
        facts.update({k:None for group in (FEATURE_GUARDS,CONFIRMATION_GUARDS) for fields in group.values() for k in fields})
        temperatures=[s["temperature_centi_c"] for s in climate["seasons"]]
        rains=[s["precipitation_mm"] for s in climate["seasons"]]
        ratio=climate["precipitation_to_pet_ppm"]
        land=terrain["height_mm"]>self.regional.terrain.plan.source.config.sea_level_m*1000
        altitude_mm=terrain["height_mm"]-self.regional.terrain.plan.source.config.sea_level_m*1000
        slope=slope_centi_degrees(terrain["slope_magnitude_ppm"])
        number=int(formation["substrates"][0][-3:])
        facts.update({"clima.temperatura_media_anual_c":climate["mean_temperature_centi_c"]/100,
            "clima.precipitacao_anual_mm":climate["annual_precipitation_mm"],
            "clima.indice_aridez":ratio/1000000 if ratio is not None else None,
            "clima.sazonalidade_precipitacao_indice_0_1":((max(rains)-min(rains))*1000000//sum(rains))/1000000 if sum(rains) else None,
            "clima.periodo_mais_quente_c":max(temperatures)/100,
            "clima.meses_cobertura_neve":None,
            "clima.regime_frio_confirmado":climate["mean_temperature_centi_c"]<=self.config.cold_regime_max_mean_centi_c,
            "clima.regime_polar_oceanico_confirmado":climate["mean_temperature_centi_c"]<=self.config.cold_regime_max_mean_centi_c,
            "terreno.altitude_m":altitude_mm/1000,
            "terreno.declividade_graus":slope/100,
            "terreno.evidencia_superficie_continental":land,
            "terreno.contexto_relevo_montanhoso":land and altitude_mm>=self.config.mountain_min_altitude_m*1000 and terrain["tectonic_context_mm"]>=self.config.mountain_min_tectonic_context_mm,
            "geologia.substrato_granitico_confirmado":None if formation["contact_fragment_pending"] else number==1,
            "geologia.substrato_carbonatico_confirmado":None if formation["contact_fragment_pending"] else number in (6,12),
            "geologia.substrato_argiloso_confirmado":None if formation["contact_fragment_pending"] else number in (8,9),
            "geologia.origem_vulcanica_confirmada":True if any(h["kind"]=="volcanic_sequence" for h in parent["history"]) else None})
        evidence={"C2":[k for k in facts if k.startswith("clima.") and facts[k] is not None],
            "T1":[k for k in facts if k.startswith("terreno.") and facts[k] is not None],
            "JR1":[k for k in facts if k.startswith("geologia.") and facts[k] is not None],
            "unknown":sorted(k for k,v in facts.items() if v is None)}
        result=self.classifier.classify(facts)
        node=cell_index(cell_at(point,self.h1.config.level))
        weights=stencil(point,self.climate.config.level)
        distances=[self.climate.ocean_distance_m[i] for i,_ in weights]
        ocean_distance=interpolate(self.climate.ocean_distance_m,weights) if all(v is not None for v in distances) else None
        data={"kind":"environment_point_e1","environment_version":1,"authority_signature":self.signature,
            "point":list(point.xyz),"probe_id":"env:"+checksum([self.signature,list(point.xyz)])[:32],
            "hierarchy":{"macro_climate_cell":list(vars(cell_at(point,self.climate.config.level)).values()),
                "regional_formation_id":formation["formation_id"],"J1_province_id":formation["parent_unit_id"],
                "scope":"point_field_not_uniform_region_or_render_tile"},
            "logical_facts":facts,"provenance":evidence,
            "physical_inputs":{"T1_height_mm":terrain["height_mm"],"T1_slope_ppm":terrain["slope_magnitude_ppm"],
                "altitude_datum":"T1_height_minus_configured_reference_sea_level",
                "slope_method":"T1_symmetric_8m_probes_integer_tangent_lookup",
                "C2_seasons":climate["seasons"],"C2_P_over_PET_ppm":ratio,
                "C2_deficit_ppm_not_used_as_P_over_PET":climate["aridity_index_ppm"],
                "continentality_ppm":climate["continentality_ppm"],"ocean_distance_m":ocean_distance,
                "snowfall_potential_mm":sum(s["snowfall_potential_mm"] for s in climate["seasons"]),
                "substrates":formation["substrates"],"JR1_checksum":checksum(formation),
                "reference_ocean_H1":self.h1.drainage.marine[node],"H1_node":node,
                "H1_is_permanent_river":False,"P1_is_vegetation":False},
            **result,"constructed_layers":[],"anomalous_layers":[],
            "additional_layer_states":{"built":{"candidato_pendente":100},"anomalous":{"candidato_pendente":50},
                "built_reason":"no_verified_exact_typed_structure","anomalous_reason":"no_specific_canonical_authorization_and_source"},
            "flora_contract":{"eligible_habitat_ids":[r["environment_id"] for r in result["results"] if r["state"]=="elegivel"],
                "vegetation_established":None,"species_catalog_loaded":False,"species_count_limit":None,"population_spawn_authorized":False},
            "persisted_classification":False,"source_fields_modified":False}
        if self.climate.config.climate_version==3:
            data['provenance']['C3']=data['provenance'].pop('C2')
            for suffix in ('seasons','P_over_PET_ppm','deficit_ppm_not_used_as_P_over_PET'):
                data['physical_inputs']['C3_'+suffix]=data['physical_inputs'].pop('C2_'+suffix)
        self.cache[key]=data
        while len(self.cache)>128:self.cache.popitem(last=False)
        return deepcopy(data)

    def mosaic(self,points):
        from .summary import summarize_environment
        points=list(points)
        if len(points)>256:
            raise ValueError("E1 mosaic budget exceeded")
        return summarize_environment(self.sample(p) for p in points)
