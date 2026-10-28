"""Small, data-driven WGS2 adapter registry. Dataset rows remain authoritative."""
import hashlib
import json

VERSION = "natural_formations_wgs2_v1"
VERSION_V2 = "natural_formations_wgs2_v2"
POLICY = "wgs2-family-opportunities-r1"

# Families share geometry and interaction adapters; individual eligibility still
# comes from each v24 row. Anomalous records are deliberately absent.
FAMILIES = {
    "open_landscape": ("EV-LOC-0020", "EV-LOC-0021", "EV-LOC-0023", "EV-LOC-0081"),
    "rock_relief": ("EV-LOC-0033", "EV-LOC-0037", "EV-LOC-0041", "EV-LOC-0193"),
    "natural_cavity": ("EV-LOC-0049", "EV-LOC-0051"),
    "arid_landscape": ("EV-LOC-0082", "EV-LOC-0084", "EV-LOC-0086"),
    "vegetation_refuge": ("EV-LOC-0225", "EV-LOC-0226"),
}
SUPPORTED = tuple(sorted(item for ids in FAMILIES.values() for item in ids))
PENDING_ONLY = ("EV-LOC-0017", "EV-LOC-0179")
EXISTING = ("EV-LOC-0036", "EV-LOC-0042", "EV-LOC-0050", "EV-LOC-0068", "EV-LOC-0236")


def _hash(seed, address, label, version=VERSION):
    raw = json.dumps([version, seed, address, label], sort_keys=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def family(archetype_id):
    return next((name for name, ids in FAMILIES.items() if archetype_id in ids), None)


def candidate(seed, address, records, *, version=VERSION):
    """5.5% local opportunity rate, then relative catalog rarity weighting."""
    if _hash(seed, address, "opportunity", version) % 1000 >= 55:
        return None
    family_members = {**FAMILIES, "established_wgs1": EXISTING}
    def weight(archetype_id):
        rarity = records[archetype_id].get("raridade", {})
        value = rarity.get("peso_relativo_referencia", 1) if isinstance(rarity, dict) else 1
        return max(1, int(float(value) * 1_000_000))
    # Separate deterministic family choice from archetype choice. Family
    # probability is the sum of catalog reference weights within that family.
    family_names = sorted(family_members)
    family_weights = [sum(weight(item) for item in family_members[name]) for name in family_names]
    slot = _hash(seed, address, "family", version) % sum(family_weights)
    chosen_family = family_names[-1]
    for name, family_weight in zip(family_names, family_weights):
        if slot < family_weight:
            chosen_family = name
            break
        slot -= family_weight
    ids = family_members[chosen_family]
    weights = [weight(item) for item in ids]
    slot = _hash(seed, address, "archetype:" + chosen_family, version) % sum(weights)
    for archetype_id, archetype_weight in zip(ids, weights):
        if slot < archetype_weight:
            return archetype_id
        slot -= archetype_weight
    raise AssertionError("weighted selection exhausted")


def eligibility(archetype_id, facts, sea_level_m):
    """Conservative physical gate; absent evidence rejects or leaves pending."""
    physical = facts.get("physical_inputs", {})
    logical = facts.get("logical_facts", {})
    height = physical.get("T1_height_mm")
    ocean = physical.get("reference_ocean_H1")
    if type(height) is not int or type(ocean) is not bool:
        return False, "pending", "confirmed_T1_H1_evidence_missing"
    if ocean or height <= sea_level_m * 1000:
        return False, "rejected", "site_not_confirmed_land"
    habitats = set(facts.get("flora_contract", {}).get("eligible_habitat_ids", []))
    slope = physical.get("T1_slope_ppm")
    required_habitats = {
        "EV-LOC-0020": "EV-BIO-CAMPO_DE_ALTITUDE", "EV-LOC-0021": "EV-BIO-SAVANA",
        "EV-LOC-0023": "EV-BIO-PASTAGEM_NATURAL",
        "EV-LOC-0081": "EV-BIO-DESERTO_DUNAS", "EV-LOC-0041": "EV-BIO-ENCOSTA_INSTAVEL",
        "EV-LOC-0082": "EV-BIO-DESERTO_PEDREGOSO",
        "EV-LOC-0084": "EV-BIO-TERRAS_ARGILOSAS_ERODIDAS", "EV-LOC-0086": "EV-BIO-DESERTO_PEDREGOSO",
        "EV-LOC-0226": "EV-BIO-ESCARPA_ROCHOSA",
    }
    required = required_habitats.get(archetype_id)
    if required and required not in habitats:
        return False, "rejected", "E1_does_not_confirm_required_habitat:" + required
    if archetype_id == "EV-LOC-0017":
        return False, "pending", "requires_persisted_Vg2_grass_population; E1_is_only_potential_habitat"
    if archetype_id in ("EV-LOC-0033", "EV-LOC-0037", "EV-LOC-0041", "EV-LOC-0193", "EV-LOC-0226") and (type(slope) is not int or slope < 1000):
        return False, "rejected", "T1_local_relief_not_confirmed"
    if archetype_id == "EV-LOC-0049":
        return False, "pending", "requires_confirmed_local_moisture_for_wet_column_feature"
    if archetype_id == "EV-LOC-0051":
        # The cavity geometry and interior are owned by this persisted WGS2
        # instance, as in the existing WGS1 cave contract; no loot is implied.
        return True, "accepted", "WGS2_owned_natural_cavity_geometry"
    if archetype_id == "EV-LOC-0179":
        return False, "pending", "requires_persisted_Vg2_moss_or_compatible_individual"
    if archetype_id == "EV-LOC-0225":
        required = {"EV-BIO-BOSQUE_ABERTO", "EV-BIO-PRADARIA"}
        if required <= habitats:
            return True, "accepted", "E1_confirms_both_ecotone_habitats"
        return False, "rejected", "E1_does_not_confirm_both_ecotone_habitats"
    return True, "accepted", "catalog_geometry_and_confirmed_terrestrial_site"
