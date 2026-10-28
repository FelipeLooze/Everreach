"""No new physical authorities. Trace the gap between real fields and extreme ecology."""
import json


def extreme_evidence(species,environment,water):
    if not species.extreme_json:raise ValueError("An extreme v22 species is required")
    contract=json.loads(species.extreme_json);f=environment["logical_facts"];p=environment["physical_inputs"]
    known={"T1_altitude_m":f["terreno.altitude_m"],"T1_slope_degrees":f["terreno.declividade_graus"],
        "T1_mountain_context":f["terreno.contexto_relevo_montanhoso"],"JR1_substrates":p["substrates"],
        "JR1_historical_volcanism":f.get("geologia.origem_vulcanica_confirmada"),
        "C3_seasonal_temperatures_c":[s["temperature_centi_c"]/100 for s in p["C3_seasons"]],
        "W1_regional_soil_mm":water["soil_mm_by_period"],"W1_reference_marine":water["macro_marine"]}
    habitat=contract["ambiente_natural_id"]
    missing=[contract["evidencia_microhabitat_obrigatoria"],"localized_nutrient_or_trophic_source"]
    if "PICO_NEVADO" in habitat:missing+=["persisted_ice_free_microfissure_not_T1_noise_or_W1_macro_snow"]
    elif "VULCANICA" in habitat:missing+=["current_activity_not_historical_JR1_sequence","localized_geothermal_or_atmospheric_nutrients"]
    elif any(t in habitat for t in ("CAVERNA","GRUTA","TUNEL","SUBTERRAN","ABISMO")):
        missing+=["actual_cavity_geometry_and_access","localized_light_or_detrital_chemical_energy"]
    elif any(t in habitat for t in ("GELEIRA","BANQUISA")):missing+=["actual_ice_geometry_not_snowfall_potential"]
    elif "DESERTO_POLAR" in habitat:missing+=["localized_thaw_pocket_and_substrate_not_air_temperature_only"]
    else:missing+=["confirmed_water_column_depth_and_trophic_or_photic_layer"]
    if contract["agua_ou_hidrologia_desconhecida_gera_pendencia"]:
        missing+=["colocated_persistent_local_water_not_H1_or_P1_throughput"]
    if species.magic=="excepcional":missing+=["authorized_exact_anomaly_and_colocated_persisted_source:"+str(species.anomaly)]
    return {"species_id":species.id,"organism_type":species.kind,"habitat_id":habitat,
        "microhabitat":contract["microhabitat_exclusivo"],"energy_requirements":contract["condicoes_energeticas_obrigatorias"],
        "known_partial_evidence":known,"missing":missing,"state":"pending","materialization_authorized":False,
        "reason":"existing_authorities_do_not_confirm_the_required_microgeometry_and_local_energy",
        "source_checksums":{"E1":environment["authority_signature"],"JR1":p["JR1_checksum"],"water":water["water_signature"]}}
