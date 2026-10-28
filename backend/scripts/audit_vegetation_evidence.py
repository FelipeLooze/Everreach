"""Audit all extreme contracts and all stockless parts; never grant occurrences."""
from collections import Counter
import json
from scripts.validate_vegetation import inputs_vg1,centers,ROOT
from scripts.calibrate_vegetation import OUT
from app.game.world.genesis.vegetation.evidence_audit import extreme_evidence
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.vegetation.catalog import load_flora_catalog


def main():
    cat=load_flora_catalog();cases=[];audits={}
    for seed in (42,0,7,2026,12345):
        v=inputs_vg1(seed);points=centers(seed)
        samples=json.loads((ROOT/f"artifacts/climate-c3-final/seed-{seed}/R1-55-samples.json").read_text())
        mountains=[p for p in samples if p["land"] and p["mountain"]]
        points["mountain"]=SurfacePoint(*max(mountains,key=lambda p:p["height_m"])["point"])
        for name,point in points.items():
            e=v.environment.sample(point);w=v.water_facts(point)
            if name in ("cold","mountain","wet"):
                cases.append({"seed":seed,"context":name,"point":list(point.xyz),"T1_altitude_m":e["logical_facts"]["terreno.altitude_m"],
                    "T1_mountain":e["logical_facts"]["terreno.contexto_relevo_montanhoso"],"JR1_substrates":e["physical_inputs"]["substrates"],
                    "annual_P_mm":e["logical_facts"]["clima.precipitacao_anual_mm"],"soil_mm":w["soil_mm_by_period"],
                    "local_ice_cavity_or_water_geometry_confirmed":False})
            if seed==42 and name=="mountain":
                audits={s.id:extreme_evidence(s,e,w) for s in cat.species.values() if s.extreme_json}
    missing=[]
    for sp in cat.species.values():
        if sp.stock is not None:continue
        for part in sp.parts():
            missing.append({"species_id":sp.id,"organism_type":sp.kind,"part_id":part["id"],"part":part["parte"],
                "item_id":part["item_id"],"source_stock":None,"source_part_max":part.get("quantidade_max"),
                "source_height_cm":sp.height_cm,"unit_mass_mg":None,"available_tissue_mass_mg":None,
                "inventory_mg_per_weight_unit":None,"tissue_pool_id":None,
                "removable_fraction_ppm":None,"max_mature_units":None,"evidence_ref":None,"status":"pending_measurement_and_review",
                "calibration_contract":"PartCalibrationV1: positive_mass + bounded_shared_tissue_pool + species_part_type + explicit_review",
                "zero_mass_or_unbounded_yield_authorized":False})
    report={"extreme_species_audited":len(audits),"extreme_occurrences_authorized":0,"real_partial_contexts":cases,
        "microhabitats_confirmed_in_full":0,"conclusion":"T1 surface relief, JR1 substrates, C3 seasons and W1 macro stores are integrable now; specialized microgeometry, ice, caves, depth, nutrients and localized light/energy remain unproven",
        "stockless_species":len({x["species_id"] for x in missing}),"stockless_parts":len(missing),
        "stockless_types":dict(Counter(s.kind for s in cat.species.values() if s.stock is None)),
        "calibrations_autoapproved":0,"real_dataset_modified":False}
    OUT.mkdir(parents=True,exist_ok=True)
    for name,obj in (("evidence-audit",report),("extreme-species-evidence",audits),("resource-calibration-proposals",missing)):
        (OUT/f"{name}.json").write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="real_partial_contexts"}),flush=True)


if __name__=="__main__":main()
