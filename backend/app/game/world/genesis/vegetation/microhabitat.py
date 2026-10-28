"""Versioned, formation-owned local modifiers for WGS2.3 campaigns.

These records are immutable evidence snapshots. They never mutate E1, C3, W1,
or regional water stores; only a Vg2 eligibility copy may consume the shade
proxy authorized by this contract.
"""
from copy import deepcopy

from app.db.models.campaign import Campaign
from app.db.models.world_natural_formations import GenesisFormationCoverageCell, GenesisNaturalFormation
from ..sphere_metric import distance_m
from ..sphere_topology import CellKey, SurfacePoint, cell_at
from ..terrain.field import checksum

VERSION = "WGS2_MICROENVIRONMENT_V1"
ORIGIN_LOOKUP_VERSION = "WGS2_ORIGIN_LOOKUP_R1"
SOLAR_PET_COUPLING_PPM = 400_000
SHELTER_SOLAR_REDUCTION_PPM = {"baixo": 100_000, "médio": 200_000, "alto": 300_000}


def _seal(payload):
    return {**payload, "signature": checksum(payload)}


def validate_contract(contract, formation):
    if not isinstance(contract, dict) or contract.get("version") != VERSION:
        raise ValueError("Unsupported WGS2 microenvironment contract")
    payload = {k: v for k, v in contract.items() if k != "signature"}
    if (contract.get("canonical_id") != formation.stable_key
            or contract.get("formation_id") != formation.id
            or contract.get("signature") != checksum(payload)):
        raise ValueError("Persisted WGS2 microenvironment identity/signature mismatch")
    return contract


def build_contract(formation, point, span_m, variations, e1_row):
    """Create a neutral-by-default contract; only catalog-backed shade activates."""
    facts = e1_row.baseline if e1_row is not None else {}
    physical = facts.get("physical_inputs", {})
    logical = facts.get("logical_facts", {})
    climate = {"indice_aridez": logical.get("clima.indice_aridez")}
    habitats = set(facts.get("flora_contract", {}).get("eligible_habitat_ids", ()))
    shelter = variations.get("grau_abrigado")
    supported = (
        formation.archetype_id == "EV-LOC-0236"
        and type(physical.get("T1_height_mm")) is int
        and type(physical.get("T1_slope_ppm")) is int
        and physical.get("reference_ocean_H1") is False
        and bool(physical.get("JR1_checksum"))
        and "EV-BIO-SEMIARIDO_ARBUSTIVO" in habitats
        and isinstance(climate.get("indice_aridez"), (int, float))
        and shelter in SHELTER_SOLAR_REDUCTION_PPM
    )
    payload = {
        "version": VERSION,
        "formation_id": formation.id,
        "canonical_id": formation.stable_key,
        "evidence": {
            "catalog_archetype": formation.archetype_id,
            "catalog_microhabitat_claim": "shaded_depression",
            "catalog_candidate_flora": ["EV-FL-1506", "EV-FL-1520"],
            "E1_signature": e1_row.baseline.get("authority_signature") if e1_row else None,
            "E1_baseline_checksum": e1_row.baseline_checksum if e1_row else None,
            "T1_height_mm": physical.get("T1_height_mm"),
            "T1_slope_ppm": physical.get("T1_slope_ppm"),
            "JR1_checksum": physical.get("JR1_checksum"),
            "regional_aridity_index": climate.get("indice_aridez"),
            "eligible_habitats": sorted(habitats),
            "shelter_degree": shelter,
        },
        "influence": {"geometry": "spherical_core_with_linear_falloff_v1",
                      "center": list(point.xyz), "radius_m": max(5, span_m // 3),
                      "coverage_span_m": span_m},
        "features": ["reduced_solar_exposure"] if supported else [],
        "modifiers": ({"solar_exposure_reduction_ppm": SHELTER_SOLAR_REDUCTION_PPM[shelter]}
                      if supported else {}),
        "status": "active" if supported else "neutral",
        "neutral_reason": None if supported else "catalog_or_E1_T1_JR1_support_not_confirmed",
        "authority_scope": "local_Vg2_eligibility_proxy_only_no_E1_C3_W1_mutation",
    }
    return _seal(payload)


def _profile_enabled(db, campaign_id):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return False
    state = campaign.playable_state or {}
    config = state.get("microhabitats", {})
    return config.get("version") == VERSION


def resolve(db, campaign_id, point):
    """Load only footprints indexed at this TP1 cell, then apply spherical falloff."""
    if not _profile_enabled(db, campaign_id):
        return None
    state = db.get(Campaign, campaign_id).playable_state or {}
    level = state.get("territory", {}).get("level")
    if type(level) is not int:
        raise ValueError("WGS2.3 microenvironment requires a persisted TP1 address level")
    address = cell_at(point, level)
    cache_key = ("WGS2_MICROENV_CANDIDATES", campaign_id, address.face, address.level, address.x, address.y)
    candidates = db.info.get(cache_key)
    if candidates is None:
        rows = (db.query(GenesisFormationCoverageCell)
            .filter_by(campaign_id=campaign_id, face=address.face, level=address.level,
                       x=address.x, y=address.y, contract_version="WGS2_COVERAGE_V2").all())
        loaded = []
        for coverage in rows:
            formation = db.get(GenesisNaturalFormation, coverage.formation_id)
            if formation is None:
                raise ValueError("Coverage references a missing WGS2 formation")
            contract = formation.data.get("microenvironment")
            if contract is None:
                continue
            validate_contract(contract, formation)
            if contract["status"] == "active":
                loaded.append((formation.stable_key, formation, contract))
        candidates = tuple(sorted(loaded, key=lambda item: item[0]))
        db.info[cache_key] = candidates
    if not candidates:
        return None
    from ..sphere_config import parse_config
    config = parse_config(state["territory"]["world_config"])
    for _, formation, contract in candidates:
        center = SurfacePoint(*contract["influence"]["center"])
        distance = distance_m(config, point, center)
        radius = contract["influence"]["radius_m"]
        if distance >= radius:
            continue
        falloff = max(0, min(1_000_000, int((radius-distance)*1_000_000//radius)))
        reduction = contract["modifiers"]["solar_exposure_reduction_ppm"]*falloff//1_000_000
        # Integer fixed-point falloff can round to zero at the fringe. Such a
        # point has no effective local modifier and must retain the exact
        # regional Vg2 path.
        if reduction <= 0:
            continue
        return {"version": VERSION, "formation_id": formation.id,
            "canonical_id": formation.stable_key, "contract_signature": contract["signature"],
            "distance_m": round(distance, 3), "influence_weight_ppm": falloff,
            "features": list(contract["features"]),
            "modifiers": {"solar_exposure_reduction_ppm": reduction},
            "evidence_signature": contract["signature"]}
    return None


def apply_to_environment(environment, context):
    """Return an eligibility-only copy; regional E1 objects stay untouched."""
    if context is None:
        return environment
    reduction = context.get("modifiers", {}).get("solar_exposure_reduction_ppm", 0)
    if type(reduction) is not int or not 0 <= reduction < 1_000_000:
        raise ValueError(f"Invalid WGS2.3 solar modifier: {reduction!r} ({type(reduction).__name__})")
    if reduction == 0:
        return environment
    local = deepcopy(environment)
    facts = local.get("logical_facts", {})
    regional_ratio = facts.get("clima.indice_aridez")
    if not isinstance(regional_ratio, (int, float)) or regional_ratio < 0:
        return environment
    pet_reduction = reduction*SOLAR_PET_COUPLING_PPM//1_000_000
    denominator = 1_000_000-pet_reduction
    facts["clima.indice_aridez"] = min(1.5, regional_ratio*1_000_000/denominator)
    local["logical_facts"] = facts
    local["local_microenvironment"] = {"version": VERSION,
        "formation_id": context["formation_id"], "canonical_id": context["canonical_id"],
        "contract_signature": context["contract_signature"],
        "regional_aridity_index": regional_ratio,
        "eligibility_aridity_index": facts["clima.indice_aridez"],
        "solar_exposure_reduction_ppm": reduction,
        "regional_authority_mutated": False}
    return local
