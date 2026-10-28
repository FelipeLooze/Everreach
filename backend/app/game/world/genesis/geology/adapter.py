"""Translate persisted J1 records into the proposed D14 logical contract."""
from ..terrain.field import checksum
from .catalog import load_catalog


def adapt_unit(unit, world_id):
    if not isinstance(world_id, str) or not world_id:
        raise ValueError("A persistent world identity is required")
    # Flags require a real recorded formation process, never a query-time fallback.
    kinds = {h["kind"] for h in unit["history"]}
    for flag, record in unit["evidence_records"].items():
        if record.get("authority") != "J1" or record.get("history_kind") not in kinds:
            raise ValueError("Geological evidence has no supporting history")
    return {"adapter_version": 1, "world_id": world_id, "region_id": unit["geological_region_id"],
            "region_kind": "physical_geological_province_not_gameplay_Region",
            "geological_unit_id": unit["geological_unit_id"], "lithology_substrate_ids": list(unit["substrates"]),
            "evidence_flags": sorted(unit["evidence_records"]), "event_instance_ids": [], "source_lineage_ids": [],
            "depth_index_0_100": unit["depth_index_0_100"], "canonical_authorizations": [],
            "formation_opportunity_id": unit["formation_opportunity_id"],
            "evidence_provenance": unit["evidence_records"], "unit_checksum": checksum(unit)}


def assess_bridge(contract, bridge):
    requirements = bridge["requisitos"]
    flags = set(contract.get("evidence_flags", []))
    missing = sorted(set(requirements["evidencias_obrigatorias_all"])-flags)
    if requirements["substrato_obrigatorio"] and not set(contract.get("lithology_substrate_ids", [])) & set(requirements["substratos_aceitos_any"]):
        missing.append("compatible_substrate")
    additional = requirements["evidencias_adicionais_any"]
    if additional and not flags.intersection(additional):
        missing.append("additional_any_evidence")
    if requirements["evento_ou_organismo_instanciado_necessario"] and not contract.get("event_instance_ids"):
        missing.append("physical_event_or_organism_instance")
    if bridge["dependencia_arcana_canonica"] and not contract.get("canonical_authorizations"):
        missing.append("canonical_authorization")
    return {"eligible": not missing, "missing": missing, "bridge_id": bridge["id"]}


def evaluate_opportunities(contract, catalog=None):
    """One opportunity per unit/material, however many routes are satisfied."""
    catalog = catalog or load_catalog()
    bridge_results = {model: assess_bridge(contract, b) for model, b in catalog["bridges"].items()}
    opportunities = []
    flags = set(contract["evidence_flags"])
    for material_id, material in catalog["materials"].items():
        primary = material["origem_condicional"]["modelo_geologico"]
        routes = []
        if bridge_results[primary]["eligible"]:
            routes.append({"route_id": "v4:"+material_id, "model": primary})
        for route in catalog["alternatives"]:
            if (route["material_id"] == material_id and bridge_results[route["origem_alternativa_modelo_id"]]["eligible"] and
                    set(route["evidencias_adicionais_necessarias_all"]) <= flags):
                routes.append({"route_id": route["id"], "model": route["origem_alternativa_modelo_id"]})
        if routes:
            identity = checksum([contract["world_id"], contract["formation_opportunity_id"], material_id])[:32]
            opportunities.append({"opportunity_id": "ore-opportunity:"+identity, "material_id": material_id,
                "geological_unit_id": contract["geological_unit_id"], "region_id": contract["region_id"],
                "formation_opportunity_id": contract["formation_opportunity_id"], "routes": routes,
                "rarity": material["raridade_proposta"], "eligible_not_instantiated": True,
                "legendary_random_generation_allowed": False})
    return {"opportunities": opportunities, "bridges": bridge_results}
