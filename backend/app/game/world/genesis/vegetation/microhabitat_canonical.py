"""Read-only WGS2.3.1 physical microhabitat resolution for new campaigns.

Candidate geometry and E1 inputs are the same authorities used by WGS2
materialization. A query never creates a formation, discovery, or plant.
"""
from math import ceil, log2
from types import SimpleNamespace
from collections import OrderedDict

from app.db.models.campaign import Campaign
from app.db.models.world_environment import GenesisEnvironmentPoint
from app.db.models.world_geology_regional import GenesisRegionalFormation
from app.db.models.world_geology import GenesisGeologicalUnit
from app.db.models.world_natural_formations import GenesisFormationCandidate, GenesisNaturalFormation
from ..sphere_metric import distance_m
from ..sphere_topology import cell_at, cell_center, face_point
from ..terrain.field import checksum
from .microhabitat import VERSION, build_contract, validate_contract

PROFILE = "world_genesis_ap1_tp1_wgs2_v4"
PROFILE_V5 = "world_genesis_ap1_tp1_wgs2_v5"
PROFILE_WGS3 = "world_genesis_ap1_tp1_wgs3_v1"
POLICY = "regional_canopy_wgs2_canonical_v1"
RESOLUTION_VERSION = "WGS2_CANONICAL_MICRO_R1"


def territory_level(config):
    """Use the same pinned TP1 scale before and after territory bootstrap."""
    return min(24, max(config.sector_level, ceil(log2(2 * config.radius_m / 1000))))


def formation_parameters(seed, key, record):
    """The V4 predictor and WGS2 materializer share these frozen parameters."""
    from ..local_formations import _hash, VERSION_WGS2_V2
    scale = record["geometria"]["escala_horizontal_m_sugerida"]
    maximum = min(3400, int(scale["max"]))
    minimum = min(maximum, int(scale["min"]))
    span = minimum + _hash(seed, key, "horizontal_span", VERSION_WGS2_V2) % (maximum-minimum+1)
    axes = record.get("variacoes_procedurais", {}).get("eixos", {})
    selected = {name: vals.get("valores_candidatos", [None])[
        _hash(seed, key, name, VERSION_WGS2_V2) % len(vals.get("valores_candidatos", [None]))]
        for name, vals in axes.items()}
    return span, selected


def _baseline(db, campaign_id, environment, point):
    from ..environment.service import (_identifier, _validate, _geological_context,
                                       seal_physical_classification)
    from ..terrain.service import query_altitude
    identifier = _identifier(environment, point)
    row = db.get(GenesisEnvironmentPoint, (campaign_id, identifier))
    if row is not None:
        _validate(row, environment, point)
        if row.changes:
            raise ValueError("E1 changes require explicit WGS2 microhabitat reconciliation")
        _geological_context(db, campaign_id, environment, point)
        if query_altitude(db, campaign_id, point)["height_mm"] != row.baseline["physical_inputs"]["T1_height_mm"]:
            raise ValueError("Persisted E1 terrain differs from canonical microhabitat")
        return row
    # A persisted JR1 overlay cannot be silently replaced by a fresh sample.
    regional_id = environment.regional.address(point)[3]
    if db.get(GenesisRegionalFormation, (campaign_id, regional_id)) is not None:
        _geological_context(db, campaign_id, environment, point)
    data = seal_physical_classification(environment.sample(point))
    parent_id = data["hierarchy"]["J1_province_id"]
    if db.get(GenesisGeologicalUnit, (campaign_id, parent_id)) is not None:
        from ..geology.regional.service import _parent_current
        _parent_current(db, campaign_id, SimpleNamespace(parent_unit_id=parent_id), environment.regional)
    if query_altitude(db, campaign_id, point)["height_mm"] != data["physical_inputs"]["T1_height_mm"]:
        raise ValueError("T1 terrain differs from canonical microhabitat")
    return SimpleNamespace(baseline=data, baseline_checksum=checksum(data))


def _candidate_geometry(db, campaign, point, sampler):
    """Return only candidate centers inside the maximum supported influence."""
    from ..local_formations import catalog, VERSION_WGS2_V2
    from ..wgs2_coverage import footprint_cells
    from ..wgs2_families import candidate
    config = sampler.environment.regional.terrain.plan.source.config
    level = territory_level(config)
    descriptor = (campaign.playable_state or {}).get("territory")
    if descriptor and (descriptor.get("level") != level or descriptor.get("world_config") != config.model_dump(mode="json")):
        raise ValueError("Canonical microhabitat TP1/world authority mismatch")
    record = catalog()["EV-LOC-0236"]
    scale = record["geometria"]["escala_horizontal_m_sugerida"]
    maximum = min(3400, int(scale["max"]))
    max_radius = max(5, maximum // 3)
    target = cell_at(point, level)
    cache = db.info.setdefault("WGS2_CANONICAL_CANDIDATES_R1", OrderedDict())
    cache_key = (campaign.id, campaign.world_seed, sampler.environment.signature,
                 config.radius_m, target.face, target.level, target.x, target.y)
    candidates = cache.get(cache_key)
    if candidates is None:
        center = cell_center(target)
        grid = 2**level
        # Every point of the spherical cube cell is within its furthest
        # corner. Include candidate centers up to one influence radius beyond
        # that bound; this covers points at edges and face seams.
        corners = (face_point(target.face, target.x+dx, target.y+dy, grid)
                   for dx in (0, 1) for dy in (0, 1))
        reach = max(distance_m(config, center, corner) for corner in corners) + max_radius + 2
        possible = footprint_cells(center, level, config.radius_m, ceil(2 * reach))
        found = []
        for cell in possible:
            address = vars(cell)
            archetype = candidate(campaign.world_seed, address, catalog(), version=VERSION_WGS2_V2)
            if archetype != "EV-LOC-0236":
                continue
            key = checksum([VERSION_WGS2_V2, campaign.world_seed, address, archetype])
            span, _ = formation_parameters(campaign.world_seed, key, record)
            found.append((key, cell, cell_center(cell), span))
        candidates = tuple(sorted(found, key=lambda item: item[0]))
        cache[cache_key] = candidates
        while len(cache) > 128:
            cache.popitem(last=False)
    else:
        cache.move_to_end(cache_key)
    result = []
    for key, cell, center, span in candidates:
        distance = distance_m(config, point, center)
        if distance < max(5, span // 3):
            result.append((key, cell, center, span, distance))
    return result, record, config


def _source_contract(db, campaign_id, campaign, sampler, key, center, span, record, config):
    from ..local_formations import _id, evaluate_context_v2, VERSION_WGS2_V2, POLICY_WGS2
    e1 = _baseline(db, campaign_id, sampler.environment, center)
    decision = evaluate_context_v2("EV-LOC-0236", e1.baseline, config.sea_level_m)
    persisted_decision = db.query(GenesisFormationCandidate).filter_by(
        campaign_id=campaign_id, stable_key=key).one_or_none()
    if persisted_decision is not None:
        valid_status = (("accepted", "materialized") if decision["accepted"] else ("rejected",))
        if (persisted_decision.id != _id(campaign_id, key, "candidate", VERSION_WGS2_V2)
                or persisted_decision.archetype_id != "EV-LOC-0236"
                or persisted_decision.generator_version != VERSION_WGS2_V2
                or persisted_decision.status not in valid_status
                or persisted_decision.decision != {**decision, "policy": POLICY_WGS2}):
            raise ValueError("Persisted WGS2 candidate differs from canonical physical evidence")
    if not decision["accepted"]:
        return None
    expected_span, selected = formation_parameters(campaign.world_seed, key, record)
    if span != expected_span:
        raise ValueError("Canonical WGS2 geometry changed during resolution")
    formation = SimpleNamespace(id=_id(campaign_id, key, "instance", VERSION_WGS2_V2),
                                stable_key=key, archetype_id="EV-LOC-0236")
    local = build_contract(formation, center, span, selected, e1)
    existing = db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign_id, stable_key=key).one_or_none()
    if existing is not None:
        persisted = existing.data.get("microenvironment")
        validate_contract(persisted, existing)
        if persisted != local:
            raise ValueError("Persisted WGS2 formation differs from canonical microhabitat")
    return local


def resolve(db, campaign_id, point, sampler):
    """Resolve physical evidence, including unmaterialized and undiscovered origins."""
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.world_profile not in (PROFILE, PROFILE_V5, PROFILE_WGS3) or sampler.config.policy != POLICY:
        raise ValueError("Canonical WGS2 microhabitats require the explicit V4 profile")
    state = campaign.playable_state
    if state is not None:
        contract = state.get("microhabitats", {})
        if contract.get("version") != VERSION or contract.get("canonical_resolution_version") != RESOLUTION_VERSION:
            raise ValueError("Canonical WGS2 microhabitat version is not pinned")
    candidates, record, config = _candidate_geometry(db, campaign, point, sampler)
    for key, cell, center, span, distance in candidates:
        # GA2/L2 already fences its batch and keeps a transaction-local E1
        # read view. Reuse the validated immutable formation source only for
        # that batch; outside it every persisted source is checked again.
        runtime = db.info.get(("L2_batch", campaign_id)) if db.info.get(("L2_advancing", campaign_id)) else None
        cache = getattr(runtime, "_wgs2_canonical_sources", None) if runtime is not None else None
        if runtime is not None and cache is None:
            cache = OrderedDict()
            runtime._wgs2_canonical_sources = cache
        if cache is not None and key in cache:
            local = cache[key]
            cache.move_to_end(key)
        else:
            local = _source_contract(db, campaign_id, campaign, sampler, key, center, span, record, config)
            if cache is not None:
                cache[key] = local
                while len(cache) > 128:
                    cache.popitem(last=False)
        if local is None or local["status"] != "active":
            continue
        radius = local["influence"]["radius_m"]
        weight = max(0, min(1_000_000, int((radius-distance)*1_000_000//radius)))
        reduction = local["modifiers"]["solar_exposure_reduction_ppm"]*weight//1_000_000
        if reduction <= 0:
            continue
        return {"version": VERSION, "formation_id": local["formation_id"], "canonical_id": key,
            "contract_signature": local["signature"], "distance_m": round(distance, 3),
            "influence_weight_ppm": weight, "features": list(local["features"]),
            "modifiers": {"solar_exposure_reduction_ppm": reduction},
            "evidence_signature": local["signature"]}
    return None
