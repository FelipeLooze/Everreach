from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest
from app.game.world.genesis.environment.catalog import load_environment_catalog,FILES
from app.game.world.genesis.environment.classifier import NaturalClassifier,evaluate_built,evaluate_anomaly
from app.game.world.genesis.environment.config import EnvironmentConfig
from app.game.world.genesis.environment.adapter import EnvironmentSampler
from app.game.world.genesis.environment.service import seal_physical_classification
from app.game.world.genesis.sphere_topology import SurfacePoint,CellKey,cell_center
from app.game.world.genesis.terrain.address import point_on_face,tile_at
from app.game.world.genesis.terrain.field import checksum
from scripts.validate_environment import environment_inputs

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def reference():
    return environment_inputs(42,63710000)


def test_only_one_active_taxonomy_and_exact_v20_files():
    c=load_environment_catalog()
    assert len(c["natural"])==len(c["rules"])==len(c["built"])==100
    assert len(c["anomalies"])==50 and c["active_records"]==250
    if "sem_candidatos_naturais_total" in c["habitat_audit"]:
        assert c["habitat_audit"]["sem_candidatos_naturais_total"]==62
    else:
        assert c["habitat_audit"]["status"]=="not_available_in_active_package"
    archive_path=ROOT/"datasets/Everreach_TODOS_Datasets_Taxonomia_Ativa_Unificada_v20.zip"
    if not archive_path.exists():
        archive_path=ROOT/"datasets/Everreach_TODOS_Datasets_Flora_Extrema_v22.zip"
    with zipfile.ZipFile(archive_path) as archive:
        for name,_ in FILES.values():
            assert archive.read("00_Taxonomia_Ambientes/"+name)==(ROOT/"datasets/00_Taxonomia_Ambientes"/name).read_bytes()
    c["rules"].clear()
    assert len(load_environment_catalog()["rules"])==100


@pytest.mark.parametrize("index",range(15))
def test_all_corrective_contract_fixtures(index):
    c=load_environment_catalog();f=c["fixtures"][index];identifier=f["ambiente_id"]
    if f["categoria"]=="natural":
        actual=NaturalClassifier(catalog=c).evaluate(identifier,f["dados"],backend_guards=False)["state"]
    elif f["categoria"]=="construido":
        actual=evaluate_built(c["built"][identifier],f["dados"],persistence_verified=True)
    else:
        actual=evaluate_anomaly(c["anomalies"][identifier],f["dados"],persistence_verified=True)
    expected=f["esperado_avaliacao"]
    if expected.startswith("candidato_pendente"):expected="candidato_pendente"
    if expected.startswith("elegivel"):expected="elegivel"
    assert actual==expected


def test_unknown_zero_and_false_are_different():
    engine=NaturalClassifier()
    facts={"clima.temperatura_media_anual_c":27,"clima.indice_aridez":1.4}
    assert engine.evaluate("EV-BIO-FLORESTA_TROPICAL_UMIDA",facts,backend_guards=False)["state"]=="candidato_pendente"
    facts["clima.precipitacao_anual_mm"]=0
    assert engine.evaluate("EV-BIO-FLORESTA_TROPICAL_UMIDA",facts,backend_guards=False)["state"]=="incompativel"
    wet={"clima.temperatura_media_anual_c":25,"clima.precipitacao_anual_mm":1900,"hidrologia.solo_saturado_confirmado":False}
    result=engine.evaluate("EV-BIO-MANGUEZAL",wet,backend_guards=False)
    assert result["state"]=="incompativel" and "hidrologia.solo_saturado_confirmado" in result["contradictions"]


def test_zero_rain_is_a_valid_hyperarid_potential_not_a_scoring_gap():
    result=NaturalClassifier().classify({"clima.temperatura_media_anual_c":-5,"clima.precipitacao_anual_mm":0,
        "clima.indice_aridez":0,"terreno.evidencia_superficie_continental":True})
    assert result["primary_potential"]=="EV-BIO-DESERTO_FRIO"
    assert result["mixture"][0]["weight_ppm"]==1000000


def test_forest_potential_needs_no_species_and_never_confirms_trees():
    engine=NaturalClassifier()
    facts={"clima.temperatura_media_anual_c":27,"clima.precipitacao_anual_mm":2600,"clima.indice_aridez":1.4,
        "clima.periodo_mais_quente_c":29,"terreno.evidencia_superficie_continental":True}
    result=engine.classify(facts)
    forest=next(r for r in result["results"] if r["environment_id"]=="EV-BIO-FLORESTA_TROPICAL_UMIDA")
    assert forest["state"]=="elegivel" and forest["vegetation_confirmed"] is False
    sealed=seal_physical_classification({**result,"probe_id":"fixture"})
    assert next(r for r in sealed["results"] if r["environment_id"]==forest["environment_id"])["state"]=="elegivel"
    assert sealed["vegetation_confirmed"] is False
    if "ambientes_sem_candidatos" in engine.catalog["habitat_audit"]:
        assert forest["environment_id"] in {x["id"] for x in engine.catalog["habitat_audit"]["ambientes_sem_candidatos"]}


def test_local_waterfall_never_replaces_primary_cover():
    facts={"clima.temperatura_media_anual_c":25,"clima.precipitacao_anual_mm":2500,"clima.indice_aridez":1.3,
        "clima.periodo_mais_quente_c":29,"terreno.evidencia_superficie_continental":True,
        "hidrologia.corpo_agua_doce_confirmado":True,"hidrologia.rede_fluvial_confirmada":True,
        "hidrologia.desnivel_hidraulico_real":True}
    result=NaturalClassifier().classify(facts)
    assert "EV-BIO-CACHOEIRA" in result["feature_layers"]
    assert result["primary_potential"]!="EV-BIO-CACHOEIRA"


def test_real_P_over_PET_mapping_and_no_snow_or_water_invention(reference):
    s=reference.sample(cell_center(CellKey(0,3,4,5)))
    assert s["logical_facts"]["clima.indice_aridez"]==s["physical_inputs"]["C2_P_over_PET_ppm"]/1000000
    for key in ("hidrologia.rede_fluvial_confirmada","hidrologia.corpo_agua_doce_confirmado","criosfera.acumulo_neve_confirmado",
                "criosfera.corpo_glaciar_persistente_confirmado","oceano.corpo_oceanico_confirmado"):
        assert s["logical_facts"][key] is None
    assert s["physical_inputs"]["P1_is_vegetation"] is False
    assert s["flora_contract"]["species_count_limit"] is None


def test_genuine_cold_energy_limited_case_remains_pending(reference):
    s=reference.sample(SurfacePoint(8,-5,-7))
    assert s["logical_facts"]["clima.indice_aridez"] is None
    assert s["primary_potential"] is None
    assert any(r["state"]=="candidato_pendente" and "criosfera.acumulo_neve_confirmado" in r["missing"] for r in s["results"])


def test_real_diversity_and_secondary_environments_without_source_changes(reference):
    before=checksum(reference.climate.to_dict()),checksum(reference.regional.macro.to_dict()),checksum(reference.regional.terrain.plan.source.to_dict())
    primary=set();eligible=set();ecotones=0
    for f in range(6):
        for y in range(8):
            for x in range(8):
                sample=reference.sample(cell_center(CellKey(f,3,x,y)))
                if sample["primary_potential"]:primary.add(sample["primary_potential"])
                eligible.update(r["environment_id"] for r in sample["results"] if r["state"]=="elegivel")
                ecotones+=sample["ecotone"]
                assert sum(x["weight_ppm"] for x in sample["mixture"]) in (0,1000000)
    assert len(primary)==13 and len(eligible)==25 and ecotones>0
    assert before==(checksum(reference.climate.to_dict()),checksum(reference.regional.macro.to_dict()),checksum(reference.regional.terrain.plan.source.to_dict()))


@pytest.mark.parametrize("radius",[6371000,63710000,637100000,1000000000000])
def test_faces_poles_LOD_and_order_are_continuous(radius):
    sampler=environment_inputs(42,radius);d=2**48
    a=point_on_face(0,d,d//2,d);b=point_on_face(2,0,d//2,d)
    assert a==b and sampler.sample(a)==sampler.sample(b)
    left=point_on_face(0,d-1,d//2,d);right=point_on_face(2,1,d//2,d)
    assert sampler.sample(left)["primary_potential"]==sampler.sample(right)["primary_potential"]
    for p in (a,SurfacePoint(0,0,1),SurfacePoint(0,0,-1)):
        result=sampler.sample(p)
        for level in (4,12,24,40):
            assert tile_at(p,level).level==level
            assert sampler.sample(p)==result
        assert sampler.sample(SurfacePoint(*(v*2 for v in p.xyz)))==result
    assert len(sampler.cache)<=128


def test_reversed_order_and_new_process_are_deterministic(reference):
    points=[cell_center(CellKey(0,3,x,4)) for x in range(8)]
    initial=[reference.sample(p) for p in points]
    fresh=EnvironmentSampler(reference.regional,reference.h1,reference.climate)
    assert [fresh.sample(p) for p in reversed(points)]==list(reversed(initial))
    code="from scripts.validate_environment import environment_inputs; from app.game.world.genesis.sphere_topology import SurfacePoint; from app.game.world.genesis.terrain.field import checksum; print(checksum(environment_inputs(42,63710000).sample(SurfacePoint(1,1,0))))"
    process=subprocess.run([sys.executable,"-c",code],cwd=ROOT/"backend",check=True,capture_output=True,text=True)
    assert process.stdout.strip()==checksum(reference.sample(SurfacePoint(1,1,0)))


def test_substrate_is_a_real_restriction_and_altitude_is_not_ignored():
    facts={"clima.temperatura_media_anual_c":10,"clima.precipitacao_anual_mm":1000,"clima.indice_aridez":0.8,
        "terreno.evidencia_superficie_continental":True,"terreno.contexto_relevo_montanhoso":True,
        "terreno.altitude_m":1000,"terreno.declividade_graus":10,"geologia.substrato_granitico_confirmado":True}
    engine=NaturalClassifier()
    assert engine.evaluate("EV-BIO-SERRA_GRANITICA",facts)["state"]=="elegivel"
    facts["geologia.substrato_granitico_confirmado"]=False
    assert engine.evaluate("EV-BIO-SERRA_GRANITICA",facts)["state"]=="incompativel"
    facts["geologia.substrato_granitico_confirmado"]=True;facts["terreno.altitude_m"]=100
    assert engine.evaluate("EV-BIO-SERRA_GRANITICA",facts)["state"]=="incompativel"


def test_ranges_configurable_explicitly_without_changing_C2(reference):
    config=EnvironmentConfig(range_overrides={"EV-BIO-DESERTO_FRIO":{"clima.precipitacao_anual_mm":[0,1]}})
    other=EnvironmentSampler(reference.regional,reference.h1,reference.climate,config)
    assert other.signature!=reference.signature
    assert other.climate is reference.climate
    with pytest.raises(ValueError):NaturalClassifier(EnvironmentConfig(range_overrides={"fake":{"x":[0,1]}}))


def test_typed_structure_proof_cannot_be_replaced_by_generic_or_planned_record():
    c=load_environment_catalog();r=c["built"]["EV-AMB-FORJA_ATIVA"]
    facts={"estrutura.id_persistente":"structure-1","estrutura.tipo_funcional_ambiente_id":"EV-AMB-FORJA_ATIVA",
        "estrutura.localizacao_mapeada_id":"anchor-1","estrutura.estado":"ativa"}
    assert evaluate_built(r,facts)=="candidato_pendente"
    facts["estrutura.estado"]="planejada"
    assert evaluate_built(r,facts,persistence_verified=True)=="candidato_pendente"
    facts["estrutura.estado"]="ativa";facts["estrutura.id_persistente"]=1
    assert evaluate_built(r,facts,persistence_verified=True)=="candidato_pendente"


def test_anomaly_authorization_wildcards_whitespace_and_origin_are_not_global_permission():
    c=load_environment_catalog();fix=next(f for f in c["fixtures"] if f["caso"]=="anomalia_certa_com_fonte")
    rule=c["anomalies"][fix["ambiente_id"]];facts=deepcopy(fix["dados"])
    assert evaluate_anomaly(rule,facts)=="candidato_pendente"
    key=rule["vinculo_canonico_especifico_obrigatorio"]["campo_autorizacao_id"]
    for value in ("* "," ALL ","generic","canon-*",""):
        facts[key]=value
        assert evaluate_anomaly(rule,facts,persistence_verified=True)=="candidato_pendente"


def test_native_mosaic_has_three_levels_without_duplicate_LOD_samples(reference):
    points=[cell_center(CellKey(0,3,x,4)) for x in range(8)]
    result=reference.mosaic(points+points)
    assert result["sample_count"]==8 and result["duplicate_samples_ignored"]==8
    assert result["macro_climate_cells"] and result["regional_formation_ids"]
    assert result["population_spawn_authorized"] is False and result["vegetation_established"] is None
    reversed_result=reference.mosaic(list(reversed(points+points)))
    assert reversed_result==result
    with pytest.raises(ValueError):reference.mosaic(points*33)


def test_altitude_uses_the_configured_sea_level_not_an_assumed_zero():
    from app.game.world.genesis.formation_plan import build_plan
    from app.game.world.genesis.formation_v4 import FormationConfigV4
    from app.game.world.genesis.hydrology.plan import build_hydrology_plan
    from app.game.world.genesis.hydrology.config import HydrologyConfig
    from app.game.world.genesis.climate.plan import build_climate_plan
    from app.game.world.genesis.climate.v2 import ClimateConfigV2
    from app.game.world.genesis.terrain.field import TerrainSampler,build_terrain_plan
    from app.game.world.genesis.geology.field import build_geology_plan
    from app.game.world.genesis.geology.regional.field import RegionalSampler
    source=build_plan(17,FormationConfigV4(radius_m=6371000,sea_level_m=500))
    terrain=TerrainSampler(build_terrain_plan(source));h1=build_hydrology_plan(source,HydrologyConfig(level=2))
    climate=build_climate_plan(source,h1,ClimateConfigV2(level=3))
    sampler=EnvironmentSampler(RegionalSampler(build_geology_plan(terrain.plan),terrain),h1,climate)
    result=sampler.sample(SurfacePoint(1,2,3))
    assert result["logical_facts"]["terreno.altitude_m"]==(result["physical_inputs"]["T1_height_mm"]-500000)/1000


def test_C1_is_never_silently_converted(reference):
    from dataclasses import replace
    from app.game.world.genesis.climate.config import ClimateConfig
    legacy=replace(reference.climate,config=ClimateConfig())
    with pytest.raises(ValueError,match="C2"):
        EnvironmentSampler(reference.regional,reference.h1,legacy)


def test_declivity_references_do_not_turn_flat_or_near_vertical_ground_into_eligible_escarpment():
    from app.game.world.genesis.environment.adapter import slope_centi_degrees
    facts={"clima.temperatura_media_anual_c":10,"clima.precipitacao_anual_mm":1000,"clima.indice_aridez":0.8,
        "terreno.evidencia_superficie_continental":True,"terreno.contexto_relevo_montanhoso":True,"terreno.altitude_m":1000}
    engine=NaturalClassifier()
    for slope in (0,60000000):
        facts["terreno.declividade_graus"]=slope_centi_degrees(slope)/100
        assert engine.evaluate("EV-BIO-ESCARPA_ROCHOSA",facts)["state"]=="incompativel"


@pytest.mark.parametrize("kwargs",[{"environment_version":True},{"environment_version":2},{"reference_profile":"EV-ECO-1.1"}])
def test_version_and_profile_pinned(kwargs):
    with pytest.raises(ValueError):EnvironmentConfig(**kwargs)
