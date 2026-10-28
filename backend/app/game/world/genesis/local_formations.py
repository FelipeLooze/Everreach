"""WGS1 local formations, tied to canonical v24 archetypes and TP1 addresses.

The selector is a pure function of world seed and physical cell. Local water
is owned here and deliberately never enters the W1/W2/P1 regional ledgers.
"""
from __future__ import annotations

import hashlib
import json
from math import cos, sin, sqrt
import zipfile
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy.orm.attributes import flag_modified

from app.db.models.location import Location, LocationConnection, LocationFeature
from app.db.models.region import Region
from app.db.models.world_natural_formations import (GenesisFormationCandidate, GenesisLocalWaterBody,
    GenesisNaturalFormation, GenesisFormationCoverageCell)
from app.db.models.world_spatial import LocationSpatialAnchor
from app.db.models.world_environment import GenesisEnvironmentPlan
from .sphere_topology import SurfacePoint, CellKey, cell_at, cell_center
from .sphere_metric import distance_m
from .terrain.field import checksum

VERSION = "natural_formations_wgs1"
PROFILE = "world_genesis_ap1_tp1_wgs1_v1"
PROFILE_V2 = "world_genesis_ap1_tp1_wgs1_v2"
PROFILE_V2_POLICY = "wgs1-contextual-exploration-r2"
SIGNAL_POLICY_V2 = "wgs1-nearby-signals-r1"
PROFILE_WGS2_V3 = "world_genesis_ap1_tp1_wgs2_v3"
PROFILE_WGS2_V4 = "world_genesis_ap1_tp1_wgs2_v4"
PROFILE_WGS2_V5 = "world_genesis_ap1_tp1_wgs2_v5"
PROFILE_WGS3_V1 = "world_genesis_ap1_tp1_wgs3_v1"
VERSION_V2 = "natural_formations_wgs1_v2"
from .wgs2_families import VERSION as VERSION_WGS2, VERSION_V2 as VERSION_WGS2_V2, POLICY as POLICY_WGS2
DATASET_SHA256 = "db4aced7cf5ed8d0a0d4df45b8def5789ce66d47d52a67411ed318e12483d3f0"
SUPPORTED = ("EV-LOC-0036", "EV-LOC-0042", "EV-LOC-0050", "EV-LOC-0068", "EV-LOC-0236")


@lru_cache(maxsize=1)
def catalog():
    archive = Path(__file__).resolve().parents[5] / "datasets" / "Everreach_v24_REENVIO.zip"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != DATASET_SHA256:
        raise ValueError("WGS1 canonical v24 package missing or checksum mismatch")
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        required={suffix:next((p for p in names if p.endswith(suffix)),None) for suffix in (
            "13_Locais_Formacoes_Fantasticas/Everreach_Locais_Fantasticos_v2.json",
            "13_Locais_Formacoes_Fantasticas/Everreach_Locais_Fantasticos_INDICE_v2.json",
            "13_Locais_Formacoes_Fantasticas/Everreach_Locais_Fantasticos_SCHEMA_v2.md",
            "13_Locais_Formacoes_Fantasticas/Everreach_Manifestacoes_Arcanas_v1.json")}
        if any(path is None for path in required.values()):
            raise ValueError("WGS1 canonical v24 location catalog not found")
        root = json.loads(zf.read(required["13_Locais_Formacoes_Fantasticas/Everreach_Locais_Fantasticos_v2.json"]))
        index=json.loads(zf.read(required["13_Locais_Formacoes_Fantasticas/Everreach_Locais_Fantasticos_INDICE_v2.json"]))
        schema=zf.read(required["13_Locais_Formacoes_Fantasticas/Everreach_Locais_Fantasticos_SCHEMA_v2.md"]).decode("utf-8-sig")
        manifestations=json.loads(zf.read(required["13_Locais_Formacoes_Fantasticas/Everreach_Manifestacoes_Arcanas_v1.json"]))
    records = {row["id"]: row for row in root["catalogo"]}
    index_ids={item["id"] for item in index["itens"]}
    if (not set(SUPPORTED) <= records.keys() or len(records) != 240
        or index_ids != records.keys() or len(manifestations["manifestacoes"]) != 56
        or "everreach.locais_formacoes.v2" not in schema):
        raise ValueError("WGS1 catalog identity/count validation failed")
    return records


def _hash(seed, key, label, version=VERSION):
    raw = json.dumps([version, seed, key, label], sort_keys=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def candidate(seed: int, address: dict):
    """At most one of five supported archetypes per ~1km TP1 cell."""
    n = _hash(seed, address, "selection") % 1000
    # Calibrated as local-cell opportunities, not dataset rarity weights.
    if n < 3: archetype = "EV-LOC-0036"       # 0.3% uncommon rock feature
    elif n < 5: archetype = "EV-LOC-0042"     # 0.2% nonmagical fantastic bridge valley
    elif n < 7: archetype = "EV-LOC-0050"     # 0.2% cave with one simple interior
    elif n < 8: archetype = "EV-LOC-0068"     # 0.1% finite instance-owned spring
    elif n < 11: archetype = "EV-LOC-0236"    # 0.3% shaded local microhabitat
    else: return None
    return archetype


def candidate_v2(seed: int, address: dict):
    """Exploration-rate v2: 5.5% of eligible cells, before context checks."""
    n = _hash(seed, address, "selection", VERSION_V2) % 1000
    if n < 12: return "EV-LOC-0036"   # uncommon natural rock landmark: 1.2%
    if n < 17: return "EV-LOC-0042"   # uncommon fantastic valley: 0.5%
    if n < 42: return "EV-LOC-0050"   # frequent natural cave: 2.5%
    if n < 50: return "EV-LOC-0068"   # uncommon local spring: 0.8%
    if n < 55: return "EV-LOC-0236"   # uncommon dry-slope microhabitat: 0.5%
    return None


def _id(cid, key, suffix, version=VERSION):
    namespace = "wgs2_" if version in (VERSION_WGS2, VERSION_WGS2_V2) else "wgs1_"
    return namespace + suffix + "_" + checksum([version, cid, key])[:24]


def evaluate_context_v2(archetype_id: str, facts: dict, sea_level_m: int):
    """Apply hard physical conflicts separately from soft preferences.

    E1/T1 facts are read-only inputs. Fantasy tags can relax morphology
    preferences but never place these land formations over open ocean.
    """
    physical = facts.get("physical_inputs", facts)
    logical = facts.get("logical_facts", {})
    height_mm = physical.get("T1_height_mm")
    marine = physical.get("reference_ocean_H1")
    slope_ppm = physical.get("T1_slope_ppm")
    tectonic_mm = physical.get("tectonic_context_mm")
    if tectonic_mm is None:
        tectonic_mm = physical.get("T1_tectonic_context_mm")
    substrates = list(physical.get("substrates") or [])
    aridity_ppm = physical.get("C2_P_over_PET_ppm")
    if aridity_ppm is None:
        aridity_ppm = logical.get("clima.indice_aridez")
        aridity_ppm = int(aridity_ppm * 1_000_000) if isinstance(aridity_ppm, (int, float)) else None
    reasons = []
    if type(height_mm) is not int or type(marine) is not bool:
        return {"accepted": False, "status": "rejected", "reasons": ["missing_confirmed_T1_or_H1_land_context"],
                "context": {"height_mm": height_mm, "reference_ocean_H1": marine}}
    land = height_mm > sea_level_m * 1000 and not marine
    if not land:
        return {"accepted": False, "status": "rejected", "reasons": ["incompatible_open_ocean_or_subsea_site"],
                "context": {"height_mm": height_mm, "reference_ocean_H1": marine}}
    reasons.append("confirmed_terrestrial_site")
    if archetype_id == "EV-LOC-0050":
        slope_proxy = logical.get("terreno.declividade_graus")
        relief = (type(slope_ppm) is int and slope_ppm >= 1_000) or (type(slope_proxy) in (int, float) and slope_proxy >= 0.1)
        if not relief:
            return {"accepted": False, "status": "rejected", "reasons": reasons+["cave_entrance_lacks_T1_local_relief"],
                    "context": {"height_mm": height_mm, "reference_ocean_H1": marine, "slope_ppm": slope_ppm}}
        reasons.append("T1_local_relief_supports_surface_entrance")
        if any(token in str(value).casefold() for value in substrates for token in ("carbonate", "karst", "volcanic")):
            reasons.append("substrate_preference_supported_by_JR1")
        else:
            reasons.append("cave_type_not_inferred_from_substrate; local geometry remains WGS1-owned")
    elif archetype_id == "EV-LOC-0042":
        reasons.append("fantastic_valley_keeps_relief_as_preference_not_blocker")
        if type(slope_ppm) is int and slope_ppm >= 1_000:
            reasons.append("T1_relief_preference_met")
        else:
            reasons.append("low_relief_allowed_by_nonmagical_fantastic_exception")
    elif archetype_id == "EV-LOC-0068":
        reasons.append("local_spring_source_is_owned_by_finite_WGS1_authority")
        if aridity_ppm is not None and aridity_ppm < 500_000:
            reasons.append("dry_region_allowed; explicit local source prevents regional-water inference")
    elif archetype_id == "EV-LOC-0236":
        reasons.append("local_microenvironment_may_diverge_from_regional_E1")
        if aridity_ppm is not None and aridity_ppm < 750_000:
            reasons.append("dry_slope_preference_met")
        else:
            reasons.append("dry_slope_preference_not_required; no flora is established")
    elif archetype_id == "EV-LOC-0036":
        reasons.append("landform_is_local_WGS1_geometry; open-ocean placement rejected")
        if type(slope_ppm) is int and slope_ppm >= 5_000:
            reasons.append("rugged_terrain_preference_met")
        else:
            reasons.append("low_relief_is_preference_only")
    else:
        return {"accepted": False, "status": "rejected", "reasons": reasons+["unsupported_archetype"], "context": {}}
    return {"accepted": True, "status": "accepted", "reasons": reasons,
        "context": {"height_mm": height_mm, "reference_ocean_H1": marine,
                    "slope_ppm": slope_ppm, "tectonic_context_mm": tectonic_mm,
                    "substrates": substrates, "aridity_ppm": aridity_ppm,
                    "E1_signature": facts.get("authority_signature")}}


def _surface_offset(point, radius_m, metres=10):
    values=tuple(float(v) for v in point.xyz)
    mag=sqrt(sum(v*v for v in values)); u=tuple(v/mag for v in values)
    ref=(0.0,0.0,1.0) if abs(u[2])<0.9 else (1.0,0.0,0.0)
    tangent=(ref[1]*u[2]-ref[2]*u[1],ref[2]*u[0]-ref[0]*u[2],ref[0]*u[1]-ref[1]*u[0])
    tn=sqrt(sum(v*v for v in tangent)); tangent=tuple(v/tn for v in tangent)
    angle=metres/radius_m
    scale=2**40
    return SurfacePoint(*(round((u[i]*cos(angle)+tangent[i]*sin(angle))*scale) for i in range(3)))


def _ensure_wgs2_coverage_access(db, campaign, exterior, instance, coverage):
    """Add one local access node when a covered TP1 cell is actually visited."""
    if coverage.access_location_id and db.get(Location, coverage.access_location_id):
        return
    origin = SurfacePoint(*exterior.genesis_site["point"])
    radius = (campaign.playable_state or {}).get("territory", {}).get("world_config", {}).get("radius_m")
    if not isinstance(radius, int) or radius <= 0:
        raise ValueError("WGS2 V2 coverage requires the persisted spherical radius")
    access_point = _surface_offset(origin, radius)
    formation_location = db.get(Location, instance.location_id)
    access_id = _id(campaign.id, instance.stable_key,
        f"cell_access_{coverage.face}_{coverage.level}_{coverage.x}_{coverage.y}", VERSION_WGS2_V2)
    access = db.get(Location, access_id)
    if access is None:
        access = Location(id=access_id, region_id=exterior.region_id,
            subregion_id=exterior.subregion_id, parent_location_id=formation_location.id,
            name="Acesso local à formação", type="genesis_formation_access", materialization_tier=2,
            description="Um trecho local da formação se estende por esta área.",
            genesis_site={"version":"territory_tp1", "cell":vars(cell_at(access_point, exterior.genesis_site["cell"]["level"])),
                          "point":list(access_point.xyz), "prepared":True,
                          "formation_version":VERSION_WGS2_V2})
        db.add(access); db.flush()
        db.add(LocationSpatialAnchor(location_id=access.id, campaign_id=campaign.id, point=list(access_point.xyz)))
        if campaign.world_profile in (PROFILE_WGS2_V3, PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1):
            # Coverage access is a real visitable point. Materialize its E1
            # snapshot now so perception can query the exact anchored ray on
            # revisits; legacy WGS2 profiles retain their previous behavior.
            from .environment.service import materialize_environment_point
            materialize_environment_point(db, campaign.id, access_point)
        key = coverage.id
        route = _id(campaign.id, instance.stable_key, f"coverage_route_{key}", VERSION_WGS2_V2)
        for source, target, a, b, suffix in ((exterior, access, origin, access_point, "out"),
                                             (access, exterior, access_point, origin, "back")):
            contract={"version":"WGS2_COVERAGE_ACCESS_V2", "selection_policy":"wgs2-overlap-priority-stable-key-r2", "formation_id":instance.id,
                "coverage_id":coverage.id, "coverage_checksum":coverage.contract_checksum,
                "from_point":list(a.xyz), "to_point":list(b.xyz),
                "distance_m":10, "metres":10}
            contract["checksum"] = checksum(contract)
            db.add(LocationConnection(id=route+"_"+suffix, from_location_id=source.id,
                to_location_id=target.id, direction="formação próxima" if suffix=="out" else "retornar",
                distance=0.01, danger=0, travel_time_modifier=1, active=True, spatial_contract=contract))
    coverage.access_location_id = access.id
    db.flush()


def _materialize_unprepared_origins_covering(db, campaign, exterior):
    """Resolve only deterministic WGS2 candidates whose bounded footprint covers this cell."""
    from .wgs2_coverage import footprint_cells
    from .territory import _site
    from .environment.service import materialize_environment_point
    address = exterior.genesis_site["cell"]
    current = CellKey(**address)
    point = SurfacePoint(*exterior.genesis_site["point"])
    territory = (campaign.playable_state or {}).get("territory", {})
    level = address["level"]
    radius_m = territory.get("world_config", {}).get("radius_m")
    if type(radius_m) is not int:
        raise ValueError("WGS2 origin lookup requires the pinned planetary radius")
    # V4 pins every origin to its cell center. Coverage membership is also
    # defined by cell centers, so the 3.4 km maximum span bounds candidate
    # centers to 1.7 km from the queried cell center. V3 retains its historic
    # wider search because its root origin can be elsewhere inside that cell.
    search_point = cell_center(current) if campaign.world_profile in (PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1) else point
    search_span = 3400 if campaign.world_profile in (PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1) else 6800
    possible = footprint_cells(search_point, level, radius_m, search_span)
    from .wgs2_families import candidate as wgs2_candidate
    records = catalog()
    matches = []
    for origin_cell in possible:
        if origin_cell == current:
            continue
        origin_address = vars(origin_cell)
        archetype_id = wgs2_candidate(campaign.world_seed, origin_address, records, version=VERSION_WGS2_V2)
        if archetype_id is None:
            continue
        key = checksum([VERSION_WGS2_V2, campaign.world_seed, origin_address, archetype_id])
        record = records[archetype_id]
        scale = record["geometria"]["escala_horizontal_m_sugerida"]
        maximum = min(3400, int(scale["max"]))
        minimum = min(maximum, int(scale["min"]))
        span = minimum + _hash(campaign.world_seed, key, "horizontal_span", VERSION_WGS2_V2) % (maximum-minimum+1)
        if campaign.world_profile in (PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1) and archetype_id == "EV-LOC-0236":
            from .vegetation.microhabitat_canonical import formation_parameters
            span, _ = formation_parameters(campaign.world_seed, key, record)
        origin_point = (SurfacePoint(*territory["root_point"])
            if campaign.world_profile not in (PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1) and vars(origin_cell) == territory.get("root_cell")
            else cell_center(origin_cell))
        actual_footprint = footprint_cells(origin_point, level, radius_m, span)
        if current in actual_footprint:
            matches.append((key, origin_cell))
    for _, origin_cell in sorted(matches, key=lambda item: item[0]):
        origin_site = _site(db, campaign.id, origin_cell, territory)
        origin_point = SurfacePoint(*origin_site.genesis_site["point"])
        materialize_environment_point(db, campaign.id, origin_point)
        instance = materialize_for_site(db, campaign, origin_site, _skip_origin_lookup=True)
        if instance is None:
            continue
        coverage = db.query(GenesisFormationCoverageCell).filter_by(
            campaign_id=campaign.id, formation_id=instance.id,
            face=current.face, level=current.level, x=current.x, y=current.y,
            contract_version="WGS2_COVERAGE_V2").one_or_none()
        if coverage is not None:
            _ensure_wgs2_coverage_access(db, campaign, exterior, instance, coverage)


def materialize_for_site(db, campaign, exterior, *, _skip_origin_lookup=False):
    """Create stable instance + existing graph access when a TP1 cell is prepared."""
    descriptor = (campaign.playable_state or {}).get("natural_formations")
    if not descriptor or descriptor.get("version") not in (VERSION, VERSION_V2, VERSION_WGS2, VERSION_WGS2_V2):
        return None
    generator_version = descriptor["version"]
    is_v2 = generator_version == VERSION_V2
    is_wgs2_v2 = generator_version == VERSION_WGS2_V2
    is_wgs2 = generator_version in (VERSION_WGS2, VERSION_WGS2_V2)
    address = exterior.genesis_site["cell"]
    canonical_v4 = is_wgs2_v2 and campaign.world_profile in (PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1)
    exterior_point = SurfacePoint(*exterior.genesis_site["point"])
    origin_point = cell_center(CellKey(**address)) if canonical_v4 else exterior_point
    def reuse_covered_instance():
        if not is_wgs2_v2:
            return None
        coverage_query = (db.query(GenesisFormationCoverageCell)
            .join(GenesisNaturalFormation, GenesisNaturalFormation.id == GenesisFormationCoverageCell.formation_id)
            .filter(GenesisFormationCoverageCell.campaign_id == campaign.id,
                GenesisFormationCoverageCell.face == address["face"],
                GenesisFormationCoverageCell.level == address["level"],
                GenesisFormationCoverageCell.x == address["x"],
                GenesisFormationCoverageCell.y == address["y"],
                GenesisFormationCoverageCell.contract_version == "WGS2_COVERAGE_V2"))
        # A public access already reached by the character is pinned. For a
        # cell with no established access, canonical formation keys break ties,
        # never campaign-scoped instance IDs.
        existing_coverage = (coverage_query.filter(
            GenesisFormationCoverageCell.access_location_id.is_not(None))
            .order_by(GenesisNaturalFormation.stable_key).first())
        if existing_coverage is None:
            existing_coverage = coverage_query.order_by(GenesisNaturalFormation.stable_key).first()
        if existing_coverage is not None:
            instance = db.get(GenesisNaturalFormation, existing_coverage.formation_id)
            if instance is not None:
                from .wgs2_coverage import persisted_coverage_valid
                rows = db.query(GenesisFormationCoverageCell).filter_by(
                    campaign_id=campaign.id, formation_id=instance.id, contract_version="WGS2_COVERAGE_V2").all()
                span = instance.data.get("dimensions", {}).get("horizontal_span_m")
                if type(span) is not int or not persisted_coverage_valid(rows, instance.stable_key, span):
                    raise ValueError("Persisted WGS2 coverage checksum mismatch; no implicit regeneration")
                _ensure_wgs2_coverage_access(db, campaign, exterior, instance, existing_coverage)
                return instance
        return None
    micro_policy = (campaign.playable_state or {}).get("microhabitats", {})
    if (is_wgs2_v2 and not _skip_origin_lookup
            and campaign.world_profile in (PROFILE_WGS2_V3, PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1)
            and micro_policy.get("origin_lookup_version") == "WGS2_ORIGIN_LOOKUP_R1"):
        _materialize_unprepared_origins_covering(db, campaign, exterior)
    if is_wgs2:
        from .wgs2_families import candidate as wgs2_candidate
        archetype_id = wgs2_candidate(campaign.world_seed, address, catalog(),
            **({"version": VERSION_WGS2_V2} if is_wgs2_v2 else {}))
    else:
        archetype_id = candidate_v2(campaign.world_seed, address) if is_v2 else candidate(campaign.world_seed, address)
    if archetype_id is None:
        return reuse_covered_instance()
    key = checksum([generator_version, campaign.world_seed, address, archetype_id]) if (is_v2 or is_wgs2) else checksum([campaign.world_seed, address, archetype_id])
    decision_row = None
    if is_v2 or is_wgs2:
        decision_row = db.query(GenesisFormationCandidate).filter_by(campaign_id=campaign.id, stable_key=key).one_or_none()
        if decision_row is not None and decision_row.status == "rejected":
            return reuse_covered_instance()
        if decision_row is None:
            from .environment.service import query_environment, materialize_environment_point
            if canonical_v4:
                materialize_environment_point(db, campaign.id, origin_point)
            facts = query_environment(db, campaign.id, origin_point)["baseline"]
            sea_level_m = (campaign.playable_state or {}).get("territory", {}).get("world_config", {}).get("sea_level_m", 0)
            if is_wgs2 and archetype_id in SUPPORTED:
                decision = evaluate_context_v2(archetype_id, facts, sea_level_m)
            elif is_wgs2:
                from .wgs2_families import eligibility
                accepted, status, reason = eligibility(archetype_id, facts, sea_level_m)
                decision = {"accepted": accepted, "status": status, "reasons": [reason],
                            "context": {"authority_signature": facts.get("authority_signature")}}
                if campaign.world_profile in (PROFILE_WGS2_V5, PROFILE_WGS3_V1):
                    physical = facts.get("physical_inputs", {})
                    decision["context"].update({
                        "height_mm": physical.get("T1_height_mm"),
                        "slope_ppm": physical.get("T1_slope_ppm"),
                        "reference_ocean_H1": physical.get("reference_ocean_H1"),
                        "substrates": facts.get("logical_facts", {}).get("substrates"),
                        "E1_eligible_habitat_ids": facts.get("flora_contract", {}).get("eligible_habitat_ids", []),
                    })
                # Candidate table's constrained status predates WGS2; pending
                # evidence remains a pinned rejection in this explicit version.
                if status == "pending":
                    decision["status"] = "rejected"
                    decision["reasons"].append("pending_evidence_not_materialized_in_" + generator_version)
            else:
                decision = evaluate_context_v2(archetype_id, facts, sea_level_m)
            decision_row = GenesisFormationCandidate(
                id=_id(campaign.id, key, "candidate", generator_version), campaign_id=campaign.id,
                stable_key=key, archetype_id=archetype_id, generator_version=generator_version,
                status=decision["status"], decision={**decision, "policy": POLICY_WGS2 if is_wgs2 else PROFILE_V2_POLICY})
            db.add(decision_row)
            db.flush()
            if not decision["accepted"]:
                return reuse_covered_instance()
    row = db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign.id, stable_key=key).one_or_none()
    if row:
        if decision_row is not None and decision_row.status != "materialized":
            decision_row.status = "materialized"
        return row
    record = catalog()[archetype_id]
    point = origin_point
    territory=(campaign.playable_state or {}).get("territory",{})
    radius_m=territory.get("world_config",{}).get("radius_m")
    if not isinstance(radius_m,int) or radius_m<=0:
        raise ValueError("WGS1 needs the pinned TP1 planetary radius")
    access_point=_surface_offset(point,radius_m)
    if canonical_v4 and access_point == exterior_point:
        access_point = _surface_offset(point, radius_m, metres=20)
    # TP1 queries validate that the exact persistent site point has E1
    # materialization. The nearby access anchor is a distinct resolved point.
    environment=None
    if db.get(GenesisEnvironmentPlan,campaign.id) is not None:
        from .environment.service import materialize_environment_point
        environment=materialize_environment_point(db,campaign.id,access_point)
    # The local formation authority establishes only its own small geometry.
    # Regional climate, altitude, geology and water plans remain untouched.
    rid = db.get(Region, exterior.region_id)
    suffix = key[:10]
    variances = record.get("variacoes_procedurais",{}).get("eixos",{})
    selected = {name: vals.get("valores_candidatos", [None])[_hash(campaign.world_seed,key,name,generator_version)%len(vals.get("valores_candidatos",[None]))]
                for name,vals in variances.items()}
    variation_text = "; ".join(f"{name.replace('_',' ')}: {value}" for name,value in selected.items())
    scale = record["geometria"]["escala_horizontal_m_sugerida"]
    span = min(700, max(int(scale["min"]), int((scale["min"]+scale["max"])/2)))
    orientation = None
    if is_wgs2:
        # V1 keeps its historic 700 m cap; V2 expands only within the selected
        # v24 archetype's suggested range and persists its sparse footprint.
        maximum = min(3400 if is_wgs2_v2 else 700, int(scale["max"]))
        minimum = min(maximum, int(scale["min"]))
        span = minimum + _hash(campaign.world_seed, key, "horizontal_span", generator_version) % (maximum-minimum+1)
        orientation = _hash(campaign.world_seed, key, "orientation", generator_version) % 360
    if canonical_v4 and archetype_id == "EV-LOC-0236":
        from .vegetation.microhabitat_canonical import formation_parameters
        span, selected = formation_parameters(campaign.world_seed, key, record)
        variation_text = "; ".join(f"{name.replace('_',' ')}: {value}" for name,value in selected.items())
    visible_visual = record["descricao_visual"]
    if campaign.world_profile in (PROFILE_WGS2_V5, PROFILE_WGS3_V1):
        from .wgs2_identity import presentation
        visible_visual, visible_variations = presentation(archetype_id, record, selected)
        variation_text = "; ".join(f"{name.replace('_',' ')}: {value}"
                                   for name,value in visible_variations.items())
    coverage_cells = None
    if is_wgs2_v2:
        # Validate the bounded footprint before flushing any formation or
        # coverage rows, so a future config that exceeds the eight-hop index
        # cannot leave a partial authoritative instance in the session.
        from .wgs2_coverage import footprint_cells
        coverage_cells = footprint_cells(point, exterior.genesis_site["cell"]["level"], radius_m, span)
    description = visible_visual + (f" Variação local: {variation_text}." if variation_text else "")
    site_base={k:v for k,v in exterior.genesis_site.items()
               if k not in ("environment_checksum","community_id","preparation_seconds")}
    site_base.update({"cell":vars(cell_at(access_point,exterior.genesis_site["cell"]["level"])),
        "point":list(access_point.xyz),"prepared":True,"formation_version":generator_version,"formation_key":key})
    if is_v2:
        site_base["coverage_contract"]={"version":"WGS1_COVERAGE_V1","cell_limit":1,"max_horizontal_span_m":700}
    elif is_wgs2 and not is_wgs2_v2:
        site_base["coverage_contract"]={"version":"WGS2_COVERAGE_V1","cell_limit":1,
            "max_horizontal_span_m":min(3400, int(record["geometria"]["escala_horizontal_m_sugerida"]["max"]))}
    elif is_wgs2_v2:
        site_base["coverage_contract"]={"version":"WGS2_COVERAGE_V2","membership":"spherical_cell_center_v1",
            "max_horizontal_span_m":min(3400, int(record["geometria"]["escala_horizontal_m_sugerida"]["max"]))}
    if environment is not None:site_base["environment_checksum"]=environment.baseline_checksum
    formation = Location(id=_id(campaign.id,key,"location",generator_version), region_id=rid.id,
        subregion_id=exterior.subregion_id, parent_location_id=exterior.id,
        name=record["nome"], type="genesis_formation", materialization_tier=2,
        description=description, genesis_site=site_base)
    db.add(formation); db.flush()
    db.add(LocationSpatialAnchor(location_id=formation.id,campaign_id=campaign.id,point=list(access_point.xyz)))
    evidence = []
    for item in record.get("habitats",{}).get("evidencias",[]):
        # These facts are created by and scoped to this persistent instance.
        evidence.append({"fact":item["fato_necessario"],"status":"instance_created",
                         "source":generator_version,"regional_authority_claimed":False})
    data = {"name":record["nome"],"category":record["categoria"],"fantasy_level":record["nivel_fantasia"],
        "point":list(access_point.xyz),"coverage":{"center":list((point if canonical_v4 else access_point).xyz),"radius_m":span//2},
        "dimensions":{"horizontal_span_m":span,"vertical_span_m":max(5,span//12),
                       **({"orientation_degrees":orientation,"geometry_type":record["geometria"].get("tipo_espacial")} if is_wgs2 else {})},
        "features":[visible_visual,*(["Arcos naturais atravessam a abertura entre os paredões."] if archetype_id=="EV-LOC-0042" else [])],
        "variations":selected,"evidence":evidence,"state":{"persisted":True},"access_location_id":formation.id,
        "interior_location_id":None,"source_flora_ids":[],"dataset_version":"v24","dataset_archetype":record,
        "origin":{"authority":generator_version,"scope":"local_instance_only","regional_geology_climate_hydrology_unchanged":True}}
    if (campaign.world_profile in (PROFILE_WGS2_V5, PROFILE_WGS3_V1) and archetype_id in
            ("EV-LOC-0050", "EV-LOC-0049", "EV-LOC-0051")
            and type(selected.get("altura_teto_m")) is int):
        data["dimensions"]["vertical_span_m"] = selected["altura_teto_m"]
    if campaign.world_profile in (PROFILE_WGS2_V5, PROFILE_WGS3_V1):
        from .wgs2_identity import facts
        data["identity"] = facts(archetype_id, record, data["dimensions"], selected,
                                 decision_row.decision if decision_row is not None else {},
                                 interior=archetype_id in ("EV-LOC-0050", "EV-LOC-0049", "EV-LOC-0051"))
    instance = GenesisNaturalFormation(id=_id(campaign.id,key,"instance",generator_version),campaign_id=campaign.id,
        location_id=formation.id,stable_key=key,archetype_id=archetype_id,generator_version=generator_version,data=data)
    db.add(instance); db.flush()
    if is_wgs2_v2 and campaign.world_profile in (PROFILE_WGS2_V3, PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1):
        from .environment.service import materialize_environment_point
        from .vegetation.microhabitat import build_contract
        source_e1 = materialize_environment_point(db, campaign.id, point)
        # Keep the snapshot in the in-flight payload: the final instance.data
        # assignment below also adds water/interior fields and would otherwise
        # discard this contract.
        data["microenvironment"] = build_contract(instance, point, span, selected, source_e1)
        for cache_key in tuple(db.info):
            if isinstance(cache_key, tuple) and len(cache_key) > 1 and cache_key[0] == "WGS2_MICROENV_CANDIDATES" and cache_key[1] == campaign.id:
                db.info.pop(cache_key, None)
    if is_wgs2_v2:
        from .wgs2_coverage import VERSION as COVERAGE_VERSION, contract_checksum
        coverage_hash = contract_checksum(key, coverage_cells, span)
        for covered in coverage_cells:
            db.add(GenesisFormationCoverageCell(
                id=_id(campaign.id, key, f"coverage_{covered.face}_{covered.level}_{covered.x}_{covered.y}", generator_version),
                campaign_id=campaign.id, formation_id=instance.id,
                access_location_id=formation.id if covered == cell_at(point, covered.level) else None,
                face=covered.face, level=covered.level, x=covered.x, y=covered.y,
                contract_version=COVERAGE_VERSION, contract_checksum=coverage_hash))
        db.flush()
        current_coverage = next((row for row in db.query(GenesisFormationCoverageCell).filter_by(
            campaign_id=campaign.id, formation_id=instance.id, face=address["face"],
            level=address["level"], x=address["x"], y=address["y"]).all()), None)
        if current_coverage is not None:
            current_coverage.access_location_id = formation.id
    # Existing Location/LocationConnection graph remains the sole travel authority.
    route_id = _id(campaign.id,key,"access",generator_version)
    formation_direction = ("indicio proximo" if is_wgs2 else
        "ind\u00edcio pr\u00f3ximo" if is_v2 and descriptor.get("signal_policy") == SIGNAL_POLICY_V2 else "ind?cio pr?ximo")
    source_origin = exterior_point if canonical_v4 else point
    if canonical_v4:
        access_metres = round(distance_m(SimpleNamespace(radius_m=radius_m), source_origin, access_point), 3)
    else:
        access_metres = 10
    for source,target,direction,source_point,target_point,suffix2 in (
        (exterior,formation,formation_direction,source_origin,access_point,"_out"),
        (formation,exterior,"exterior",access_point,source_origin,"_back")):
        contract={"version":"WGS2_LOCAL_ACCESS" if is_wgs2 else "WGS1_LOCAL_ACCESS","formation_id":instance.id,
                "from_point":list(source_point.xyz),"to_point":list(target_point.xyz),"distance_m":access_metres,"metres":access_metres}
        contract["checksum"]=checksum(contract)
        db.add(LocationConnection(id=route_id+suffix2,
            from_location_id=source.id,to_location_id=target.id,direction=direction,
            distance=access_metres/1000,danger=0,travel_time_modifier=1,active=True,
            spatial_contract=contract))
    db.add(LocationFeature(id=_id(campaign.id,key,"feature",generator_version),location_id=formation.id,
        name="Formação geográfica",description=visible_visual,visible=True))
    if archetype_id == "EV-LOC-0068":
        # Water is a separately-originated local stock, never a W1/W2/P1 debit.
        source_origin=f"{generator_version}:generated_local_spring:{key}"
        db.add(GenesisLocalWaterBody(formation_id=instance.id,campaign_id=campaign.id,
            capacity_litres=12000,stored_litres=12000,source_origin=source_origin,revision=0))
        data["water"]={"capacity_litres":12000,"stored_litres":12000,"source_origin":source_origin,
                       "regional_hydrology_credit":False}
    if archetype_id in ("EV-LOC-0050", "EV-LOC-0049", "EV-LOC-0051"):
        interior_name, interior_description = {
            "EV-LOC-0050": ("Galeria interior", "Uma cavidade natural baixa se abre em tres passagens curtas."),
            "EV-LOC-0049": ("Salao interior", "Uma camara natural ampla possui colunas rochosas irregulares."),
            "EV-LOC-0051": ("Poco obliquo", "Uma entrada inclinada desce por um trecho curto de cavidade natural."),
        }[archetype_id]
        interior = Location(id=_id(campaign.id,key,"interior",generator_version),region_id=rid.id,
            subregion_id=exterior.subregion_id,parent_location_id=formation.id,
            name=interior_name,type="genesis_formation_interior",materialization_tier=3,
            description=interior_description,
            genesis_site={**formation.genesis_site,"interior":True})
        db.add(interior);db.flush()
        db.add(LocationSpatialAnchor(location_id=interior.id,campaign_id=campaign.id,point=list(access_point.xyz)))
        data["interior_location_id"]=interior.id
        db.add(LocationFeature(id=_id(campaign.id,key,"interior_feature",generator_version),location_id=interior.id,
            name="Cavidade natural",description=interior_description+" Sem conteudo presumido.",visible=True))
        for source,target,direction,suffix2,source_point,target_point in (
            (formation,interior,"entrar","_enter",access_point,access_point),
            (interior,formation,"sair","_exit",access_point,access_point)):
            contract={"version":"WGS2_LOCAL_ACCESS" if is_wgs2 else "WGS1_LOCAL_ACCESS","formation_id":instance.id,
                "from_point":list(source_point.xyz),"to_point":list(target_point.xyz),"distance_m":10,"metres":10}
            contract["checksum"]=checksum(contract)
            db.add(LocationConnection(id=route_id+suffix2,from_location_id=source.id,to_location_id=target.id,
                direction=direction,distance=0.01,danger=0,travel_time_modifier=1,active=True,
                spatial_contract=contract))
    if campaign.world_profile in (PROFILE_WGS2_V5, PROFILE_WGS3_V1) and archetype_id in ("EV-LOC-0023", "EV-LOC-0082"):
        # These two catalog records specify observable surface features and
        # permit subareas. Establish one small, instance-owned walking route
        # only when the sampled horizontal geometry can contain it. No
        # vegetation, water, shelter benefit or resource is inferred.
        minimum_span = 300 if archetype_id == "EV-LOC-0023" else 100
        if record["geometria"].get("subareas_potenciais") and span >= minimum_span:
            label, direction, description = {
                "EV-LOC-0023": ("Faixas de solo escuro", "faixas escuras",
                                  "Faixas de solo escuro cruzam esta parte da campina."),
                "EV-LOC-0082": ("Sob o arco rochoso", "sob o arco",
                                  "A face inferior do arco rochoso sombreia este trecho do chão."),
            }[archetype_id]
            subpoint = _surface_offset(access_point, radius_m, metres=min(40, span//8))
            subdistance = round(distance_m(SimpleNamespace(radius_m=radius_m), access_point, subpoint), 3)
            subarea = Location(id=_id(campaign.id,key,"subarea",generator_version), region_id=rid.id,
                subregion_id=exterior.subregion_id, parent_location_id=formation.id,
                name=label, type="genesis_formation_subarea", materialization_tier=3,
                description=description,
                genesis_site={**formation.genesis_site,"cell":vars(cell_at(subpoint,address["level"])),
                              "point":list(subpoint.xyz),"subarea":True})
            db.add(subarea); db.flush()
            db.add(LocationSpatialAnchor(location_id=subarea.id,campaign_id=campaign.id,point=list(subpoint.xyz)))
            db.add(LocationFeature(id=_id(campaign.id,key,"subarea_feature",generator_version),
                location_id=subarea.id,name=label,description=description,visible=True))
            for source,target,edge_direction,suffix2,source_point,target_point in (
                (formation,subarea,direction,"_subarea_enter",access_point,subpoint),
                (subarea,formation,"voltar","_subarea_exit",subpoint,access_point)):
                contract={"version":"WGS2_LOCAL_ACCESS","formation_id":instance.id,
                    "from_point":list(source_point.xyz),"to_point":list(target_point.xyz),
                    "distance_m":subdistance,"metres":subdistance}
                contract["checksum"]=checksum(contract)
                db.add(LocationConnection(id=route_id+suffix2,from_location_id=source.id,
                    to_location_id=target.id,direction=edge_direction,distance=subdistance/1000,
                    danger=0,travel_time_modifier=1,active=True,spatial_contract=contract))
            data["subarea_location_ids"]=[subarea.id]
    # JSON columns are not mutable-tracked; assign a new object so late
    # water/interior fields are persisted after the initial row insert.
    instance.data=dict(data)
    flag_modified(instance,"data")
    if decision_row is not None:
        decision_row.status = "materialized"
    db.flush()
    return instance


def nearby_signals(db, campaign, exterior):
    """Return truthful, non-coordinate clues for accepted formations one TP1 edge away.

    This policy is pinned only onto newly started WGS1 v2 campaigns. It probes
    at most the four already-connected neighboring cells, and only cells whose
    deterministic selector produced a candidate. It reuses E1 snapshots,
    candidate decisions and the existing Location/LocationConnection graph.
    A clue does not grant discovery; the player still travels through the
    ordinary adjacent TP1 route and then discovers the formation by observing.
    """
    descriptor = (campaign.playable_state or {}).get("natural_formations", {})
    is_wgs2_v2 = descriptor.get("version") == VERSION_WGS2_V2 and descriptor.get("selection_policy") == POLICY_WGS2
    is_wgs2 = descriptor.get("version") in (VERSION_WGS2, VERSION_WGS2_V2) and descriptor.get("selection_policy") == POLICY_WGS2
    if ((not is_wgs2 and (descriptor.get("version") != VERSION_V2
            or descriptor.get("signal_policy") != SIGNAL_POLICY_V2))
            or exterior.genesis_site is None):
        return []
    outgoing = (db.query(LocationConnection)
        .filter(LocationConnection.from_location_id == exterior.id,
                LocationConnection.active.is_(True))
        .all())
    directions = {
        "EV-LOC-0036": "Uma roda de pinaculos rochosos circunda uma abertura ao {direction}.",
        "EV-LOC-0042": "Arcos naturais parecem ligar penhascos ao {direction}.",
        "EV-LOC-0050": "Uma abertura escura na rocha chama a atencao ao {direction}.",
        "EV-LOC-0068": "Agua parece emergir de uma fissura ao {direction}.",
        "EV-LOC-0236": "Uma depressao sombreada se destaca na encosta ao {direction}.",
    }
    if is_wgs2:
        from .wgs2_families import SUPPORTED as WGS2_SUPPORTED, candidate as wgs2_candidate
        if campaign.world_profile in (PROFILE_WGS2_V5, PROFILE_WGS3_V1):
            from .wgs2_identity import CLUES
            directions.update(CLUES)
        else:
            directions.update({item: "Uma formacao natural distinta marca a paisagem ao {direction}." for item in WGS2_SUPPORTED})
    found = []
    seen = set()
    for edge in outgoing:
        destination = db.get(Location, edge.to_location_id)
        site = destination.genesis_site if destination is not None else None
        cell = site.get("cell") if site else None
        cell_key = tuple(cell.get(k) for k in ("face", "level", "x", "y")) if isinstance(cell, dict) else None
        if (not site or site.get("version") != "territory_tp1"
                or cell == exterior.genesis_site.get("cell")
                or cell_key is None or cell_key in seen):
            continue
        seen.add(cell_key)
        archetype = wgs2_candidate(campaign.world_seed, cell, catalog(),
            **({"version": VERSION_WGS2_V2} if is_wgs2_v2 else {})) if is_wgs2 else candidate_v2(campaign.world_seed, cell)
        if archetype is None:
            continue
        stable_key = checksum([VERSION_WGS2_V2 if is_wgs2_v2 else VERSION_WGS2 if is_wgs2 else VERSION_V2, campaign.world_seed, cell, archetype])
        decision = (db.query(GenesisFormationCandidate)
            .filter_by(campaign_id=campaign.id, stable_key=stable_key).one_or_none())
        if decision is not None and decision.status == "rejected":
            continue
        if decision is None:
            from .environment.service import materialize_environment_point
            point = SurfacePoint(*site["point"])
            materialize_environment_point(db, campaign.id, point)
        instance = materialize_for_site(db, campaign, destination)
        if instance is not None:
            if campaign.world_profile == PROFILE_WGS3_V1 and instance.archetype_id == "EV-LOC-0068":
                from .local_water import contract
                if not contract(db, instance)["physical_water_present"]:
                    continue
            found.append(directions[instance.archetype_id].format(direction=edge.direction or "proximo"))
    return found


def inspect_current(db, character_id):
    from app.db.models.character import Character
    from app.db.models.location import Location
    actor=db.get(Character,character_id)
    row=db.query(GenesisNaturalFormation).filter_by(location_id=actor.location_id).one_or_none()
    if row is None:
        loc=db.get(Location,actor.location_id)
        if loc and loc.parent_location_id:
            row=db.query(GenesisNaturalFormation).filter_by(location_id=loc.parent_location_id).one_or_none()
    if row is None:
        return None
    data=row.data
    current=db.get(Location,actor.location_id)
    features=data["features"]
    if current is not None and current.type in ("genesis_formation_interior", "genesis_formation_subarea"):
        local_features=(db.query(LocationFeature).filter_by(location_id=current.id,visible=True)
                        .order_by(LocationFeature.name).all())
        features=[f"{feature.name}: {feature.description}" for feature in local_features]
    result={"instance_id":row.id,"archetype_id":row.archetype_id,"name":data["name"],
        "features":features,"dimensions":data["dimensions"],"evidence":data["evidence"],
        "water":None}
    if "identity" in data:
        from app.db.models.location import CharacterConnectionDiscovery
        result["identity"] = data["identity"]
        result["known_accesses"] = [direction for (direction,) in db.query(LocationConnection.direction)
            .join(CharacterConnectionDiscovery, CharacterConnectionDiscovery.connection_id == LocationConnection.id)
            .filter(LocationConnection.from_location_id == current.id,
                    LocationConnection.active.is_(True),
                    CharacterConnectionDiscovery.character_id == character_id).all()]
    water=db.get(GenesisLocalWaterBody,row.id)
    if water:
        result["water"]={"stored_litres":water.stored_litres,"capacity_litres":water.capacity_litres,
            "source_origin":water.source_origin,"regional_hydrology_credit":False}
    from app.db.models.campaign import Campaign
    campaign = db.get(Campaign, actor.campaign_id)
    if campaign is not None and campaign.world_profile == PROFILE_WGS3_V1 and row.archetype_id == "EV-LOC-0068":
        from .local_water import contract, public_facts
        source = contract(db, row)
        result["water_source"] = public_facts(source)
        result["water"] = None  # Same stock, represented once in WGS3 output.
        if not source["physical_water_present"]:
            result["features"] = ["A fissura da nascente permanece, mas não há água visível neste estoque local."]
    return result


def interact_current(db, character_id):
    """Inspect/touch only; no loot, extraction, or unmodeled resource transfer."""
    result=inspect_current(db,character_id)
    if result is None:
        raise ValueError("Nenhuma formação local explorável está neste local.")
    result["interaction"]="A formação foi examinada; nenhum recurso foi extraído nem transferido."
    if result.get("water_source"):
        result["interaction"] = ("A fonte foi examinada. O inventário ainda não possui recipiente com capacidade "
                                 "líquida autoritativa; nenhuma água foi transferida.")
    if "identity" in result:
        result["investigated"] = {"geometry_type": result["identity"]["geometry_type"],
            "focus": result["identity"]["investigation_focus"],
            "horizontal_span_m": result["identity"]["horizontal_span_m"],
            "catalog_variations": result["identity"]["catalog_variations"],
            "confirmed_physical": result["identity"]["confirmed_physical"]}
    return result
