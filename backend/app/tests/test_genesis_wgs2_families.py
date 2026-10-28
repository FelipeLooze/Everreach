from app.game.world.genesis.wgs2_families import FAMILIES, SUPPORTED, VERSION, candidate, eligibility, family
from app.game.world.genesis.local_formations import _id, catalog
from app.schemas.campaign import CampaignCreateRequest


def test_wgs2_family_registry_is_non_anomalous_sized_and_reusable():
    assert len(FAMILIES) == 5
    assert len(SUPPORTED) == 15
    assert all(len(ids) >= 2 for ids in FAMILIES.values())
    assert all(item.startswith("EV-LOC-") for item in SUPPORTED)
    assert all(family(item) for item in SUPPORTED)
    rows = catalog()
    assert all(item in rows and rows[item]["nivel_fantasia"] != "anomalo" for item in SUPPORTED)


def test_candidate_is_deterministic_and_uses_explicit_version():
    rows = {item: {"raridade": {"peso_relativo_referencia": 1}} for item in (*SUPPORTED,
        "EV-LOC-0036", "EV-LOC-0042", "EV-LOC-0050", "EV-LOC-0068", "EV-LOC-0236")}
    address = {"face": 5, "level": 12, "x": 203, "y": 990}
    first = candidate(42, address, rows)
    assert first == candidate(42, address, rows)
    assert first is None or first in rows
    assert VERSION == "natural_formations_wgs2_v1"
    assert _id("campaign", "key", "location", VERSION).startswith("wgs2_location_")
    assert _id("campaign", "key", "location").startswith("wgs1_location_")


def test_candidate_results_do_not_depend_on_evaluation_order():
    ids = (*SUPPORTED, "EV-LOC-0036", "EV-LOC-0042", "EV-LOC-0050", "EV-LOC-0068", "EV-LOC-0236")
    rows = {item: {"raridade": {"peso_relativo_referencia": 1}} for item in ids}
    addresses = [{"face": 2, "level": 12, "x": x, "y": 871} for x in range(40)]
    forward = {tuple(sorted(address.items())): candidate(2026, address, rows) for address in addresses}
    reverse = {tuple(sorted(address.items())): candidate(2026, address, rows) for address in reversed(addresses)}
    assert forward == reverse
    assert CampaignCreateRequest(name="WGS2", world_profile="world_genesis_ap1_tp1_wgs2_v1", world_seed=42).world_profile.endswith("wgs2_v1")


def test_context_gate_requires_confirmed_physics_and_habitat():
    land = {"physical_inputs": {"T1_height_mm": 250000, "reference_ocean_H1": False,
                                "T1_slope_ppm": 2000},
            "flora_contract": {"eligible_habitat_ids": ["EV-BIO-PRADARIA"]}}
    assert eligibility("EV-LOC-0017", land, 0)[1] == "pending"
    assert eligibility("EV-LOC-0081", land, 0)[0] is False
    assert eligibility("EV-LOC-0037", {**land, "physical_inputs": {**land["physical_inputs"], "T1_slope_ppm": 0}}, 0)[0] is False
    assert eligibility("EV-LOC-0049", land, 0)[1] == "pending"
    assert eligibility("EV-LOC-0051", land, 0)[0] is True
    assert eligibility("EV-LOC-0017", land, 0)[1] == "pending"
    assert eligibility("EV-LOC-0179", land, 0)[1] == "pending"
    assert eligibility("EV-LOC-0017", {"physical_inputs": {}}, 0)[1] == "pending"
