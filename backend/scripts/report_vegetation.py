"""Summarize measured Vg1 outputs and explicitly enumerate unproven catalog rules."""
from collections import Counter
import json
from scripts.validate_vegetation import OUT,ROOT,SCALES
from app.game.world.genesis.vegetation.catalog import load_flora_catalog


def main():
    seeds=(42,0,7,2026,12345);rows=[];presence=set();formed=0;patches=0
    for seed in seeds:
        root=OUT/f"seed-{seed}";a=json.loads((root/"ecological_v1/report.json").read_text());b=json.loads((root/"exploration_mosaic_v1/report.json").read_text())
        communities=json.loads((root/"exploration_mosaic_v1/communities.json").read_text(encoding="utf-8"))
        presence.update(p["species_id"] for s in communities.values() for p in s["populations"])
        formed+=b["established_patches"];patches+=b["communities"]
        rows.append({"seed":seed,"ecological_species":a["species_established"],"directed_species":b["species_established"],
            "ecological_dominants":a["dominant_species"],"directed_dominants":b["dominant_species"],
            "physical_patches":b["communities"],"established_communities":b["established_patches"],
            "land_weighted_mean_cover_percent":b["global_land_weighted_cover_ppm"]/10000,
            "reference_land_established_area_fraction":b["global_land_established_area_fraction"],
            "cover_ppm_range":b["cover_ppm_range"],"density_per_ha_range":b["density_per_ha_range"],
            "physiognomies":b["physiognomies"],"queries_seconds":{"ecological":a["queries_seconds"],"directed":b["queries_seconds"]},
            "moderate_route_dominance_changes":{str(k):[a["routes"]["moderate"][str(k)]["dominance_changes"],b["routes"]["moderate"][str(k)]["dominance_changes"]] for k in SCALES}})
    catalog=load_flora_catalog();blocked={};counts=Counter();stockless=0
    for s in catalog.species.values():
        reasons=[]
        if s.magic=="excepcional":reasons.append("exact_authorized_persisted_anomaly_source:"+str(s.anomaly))
        if s.extreme_json:reasons.append("localized_extreme_microhabitat_geometry_energy_and_substrate")
        if s.kind in ("alga","junco","consorcio_simbiotico"):reasons.append("localized_water_or_special_energy_source")
        if s.kind=="fungo":reasons.append("localized_detrital_energy")
        if s.kind=="trepadeira":reasons.append("localized_established_support")
        if s.temperature is None or s.rain is None:reasons.append("missing_required_species_climate_reference")
        if not s.habitats:reasons.append("no_natural_host_profile")
        if s.stock is None:stockless+=1
        if reasons:
            blocked[s.id]={"kind":s.kind,"reasons":reasons,"seen_in_measured_communities":s.id in presence}
            counts.update(reason.split(":")[0] for reason in reasons)
    assert not presence.intersection(blocked)
    result={"seeds":rows,"catalog_species":3096,"unique_species_established_in_measured_regions":len(presence),
        "established_community_patches":formed,"all_physical_patches":patches,"generated_individuals_by_statistics":0,
        "catalog_stock_unknown_species":stockless,"blocked_catalog_species":len(blocked),"blocking_reasons_not_disjoint":dict(counts),
        "meaning":"generated finite founder populations persisted as signed offline snapshots; actual database materialization and harvest separately demonstrated",
        "area_weighting":"cube-sphere solid angles; global cover over nonmarine W1 reference probes, not a census of local coastlines",
        "sampling_limits":"384 global probes plus five deliberately contrasting windows and routes per seed; regional counts are not planetary prevalence"}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"comparison.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (OUT/"pending-species.json").write_text(json.dumps(blocked,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"established-species.json").write_text(json.dumps(sorted(presence),indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="seeds"}),flush=True)


if __name__=="__main__":main()
