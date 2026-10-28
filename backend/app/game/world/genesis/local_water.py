"""WGS3.1 read-only projection of an existing formation-owned water stock.

No W1/W2/P1 quantity is relocated and no second mutable water row is made.
"""
from app.db.models.campaign import Campaign
from app.db.models.location import Location
from app.db.models.world_natural_formations import GenesisLocalWaterBody, GenesisNaturalFormation
from app.db.models.world_spatial import LocationSpatialAnchor

from .terrain.field import checksum

PROFILE = "world_genesis_ap1_tp1_wgs3_v1"
VERSION = "WGS3_LOCAL_WATER_R1"


def contract(db, formation):
    """Return the current signed source state, never the stale creation JSON."""
    if formation.archetype_id != "EV-LOC-0068":
        return None
    row = db.get(GenesisLocalWaterBody, formation.id)
    location = db.get(Location, formation.location_id)
    anchor = db.get(LocationSpatialAnchor, formation.location_id)
    if row is None or location is None or anchor is None:
        raise ValueError("Canonical local spring lacks its persisted stock or anchor")
    expected_origin = f"{formation.generator_version}:generated_local_spring:{formation.stable_key}"
    coverage = formation.data.get("coverage")
    if (row.campaign_id != formation.campaign_id or row.source_origin != expected_origin
            or type(row.capacity_litres) is not int or type(row.stored_litres) is not int
            or not 0 <= row.stored_litres <= row.capacity_litres or row.capacity_litres <= 0
            or type(row.revision) is not int or row.revision < 0
            or anchor.campaign_id != formation.campaign_id
            or formation.data.get("point") != anchor.point
            or not isinstance(coverage, dict)
            or type(coverage.get("radius_m")) is not int or coverage["radius_m"] <= 0
            or not isinstance(coverage.get("center"), list) or len(coverage["center"]) != 3):
        raise ValueError("Persisted local spring authority differs from its formation")
    source_key = checksum([VERSION, formation.stable_key, formation.archetype_id])
    state = {"version": VERSION, "source_key": source_key,
        "formation_id": formation.id, "archetype_id": formation.archetype_id,
        "origin_authority": row.source_origin, "origin_scope": "local_formation_only",
        "source_type": "finite_local_spring", "location_id": location.id,
        "point": list(anchor.point), "coverage": coverage,
        "volume_unit": "litre", "capacity_litres": row.capacity_litres,
        "available_litres": row.stored_litres, "revision": row.revision,
        "physical_water_present": row.stored_litres > 0,
        "observable_at_source": row.stored_litres > 0,
        "accessible_at_source": True, "collectable": False,
        "stored_in_container": False, "consumed_or_transferred": False,
        "flow_confirmed": False, "potability_confirmed": False,
        "recharge_authorized": False, "regional_water_ledger_credit": False}
    state["signature"] = checksum([state, formation.campaign_id])
    return state


def public_facts(state):
    """Current-place facts only; no coordinates or internal origin addresses."""
    return {key: state[key] for key in ("version", "source_key", "source_type",
        "volume_unit", "capacity_litres", "available_litres", "revision",
        "physical_water_present", "observable_at_source", "accessible_at_source",
        "collectable", "stored_in_container", "consumed_or_transferred",
        "flow_confirmed", "potability_confirmed", "recharge_authorized",
        "signature")}


def current_place_fact(db, campaign_id, location_id):
    """Replace stale creation descriptions in narrator context at this source."""
    location = db.get(Location, location_id)
    if location is None or not location.type.startswith("genesis_formation"):
        return None
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.world_profile != PROFILE:
        return None
    formation = db.query(GenesisNaturalFormation).filter_by(location_id=location.id).one_or_none()
    if formation is None and location.parent_location_id:
        formation = db.query(GenesisNaturalFormation).filter_by(location_id=location.parent_location_id).one_or_none()
    if formation is None or formation.archetype_id != "EV-LOC-0068":
        return None
    state = contract(db, formation)
    return (f"Fissura com água local visível; estoque atual {state['available_litres']} "
            f"de {state['capacity_litres']} litros. Fluxo e potabilidade não confirmados."
            if state["physical_water_present"] else
            "Fissura da nascente sem água visível no estoque local atual.")
