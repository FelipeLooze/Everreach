from types import SimpleNamespace

import pytest

from app.db.models.campaign import Campaign
from app.db.models.location import Location
from app.db.models.region import Region
from app.db.models.world_natural_formations import GenesisFormationCoverageCell, GenesisNaturalFormation
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.sphere_topology import SurfacePoint, cell_at
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.vegetation.field import eligibility
from app.game.world.genesis.vegetation.catalog import load_flora_catalog
from app.game.world.genesis.vegetation.microhabitat import (
    VERSION, apply_to_environment, build_contract, resolve, validate_contract,
)
from app.game.world.genesis.wgs2_coverage import VERSION as COVERAGE_VERSION


def _e1_facts(aridity=0.14):
    return {
        "authority_signature": "e1-test-signature",
        "physical_inputs": {
            "T1_height_mm": 900_000,
            "T1_slope_ppm": 80_000,
            "reference_ocean_H1": False,
            "JR1_checksum": "jr1-test-checksum",
        },
        "logical_facts": {
            "clima.indice_aridez": aridity,
            "clima.temperatura_media_anual_c": 20.0,
            "clima.precipitacao_anual_mm": 280.0,
            "terreno.evidencia_superficie_continental": True,
        },
        "flora_contract": {"eligible_habitat_ids": ["EV-BIO-SEMIARIDO_ARBUSTIVO"]},
    }


def _environment(aridity=0.14):
    return {
        "logical_facts": {
            "clima.indice_aridez": aridity,
            "clima.temperatura_media_anual_c": 20.0,
            "clima.precipitacao_anual_mm": 280.0,
            "terreno.evidencia_superficie_continental": True,
        },
        "flora_contract": {"eligible_habitat_ids": ["EV-BIO-SEMIARIDO_ARBUSTIVO"]},
        "physical_inputs": {"substrates": ["rock"], "C3_seasons": [{"temperature_centi_c": 2000}]},
    }


def test_contract_is_neutral_without_catalog_and_e1_evidence():
    formation = SimpleNamespace(id="f1", stable_key="stable-f1", archetype_id="EV-LOC-0236")
    row = SimpleNamespace(baseline={}, baseline_checksum="e1-checksum")
    contract = build_contract(formation, SurfacePoint(1, 0, 0), 900, {}, row)
    assert contract["status"] == "neutral"
    assert contract["features"] == []
    validate_contract(contract, formation)
    with pytest.raises(ValueError, match="signature"):
        validate_contract({**contract, "modifiers": {"solar_exposure_reduction_ppm": 999999}}, formation)


def test_water_archetype_does_not_create_an_unproven_moisture_modifier():
    formation = SimpleNamespace(id="spring-f1", stable_key="stable-spring-f1", archetype_id="EV-LOC-0068")
    row = SimpleNamespace(baseline={**_e1_facts(), "confirmed_local_water": True},
                          baseline_checksum="e1-checksum")
    contract = build_contract(formation, SurfacePoint(1, 0, 0), 900, {"grau_abrigado": "alto"}, row)
    assert contract["status"] == "neutral"
    assert contract["features"] == []
    assert contract["modifiers"] == {}


def test_supported_shade_changes_only_local_vg2_eligibility_copy():
    formation = SimpleNamespace(id="f1", stable_key="stable-f1", archetype_id="EV-LOC-0236")
    row = SimpleNamespace(baseline={**_e1_facts(), "authority_signature": "e1-test-signature"},
                          baseline_checksum="e1-checksum")
    contract = build_contract(formation, SurfacePoint(1, 0, 0), 900, {"grau_abrigado": "alto"}, row)
    assert contract["status"] == "active"
    assert contract["evidence"]["regional_aridity_index"] == 0.14
    regional = _environment()
    local = apply_to_environment(regional, {
        "formation_id": "f1", "canonical_id": "stable-f1", "contract_signature": contract["signature"],
        "modifiers": {"solar_exposure_reduction_ppm": 300_000},
    })
    assert regional["logical_facts"]["clima.indice_aridez"] == 0.14
    assert local["logical_facts"]["clima.indice_aridez"] > 0.15
    assert local["logical_facts"]["clima.precipitacao_anual_mm"] == 280.0
    assert local["local_microenvironment"]["regional_authority_mutated"] is False
    water = {"macro_marine": False, "ET_mm": 120.0, "soil_mm_by_period": [20, 35, 40, 25]}
    species = load_flora_catalog().species["EV-FL-1506"]
    assert eligibility(species, regional, water)[0] == "incompatible"
    assert eligibility(species, local, water)[0] == "eligible"


def test_microenvironment_resolves_only_inside_persisted_spherical_influence(db_session):
    db = db_session
    world = FormationConfigV4().model_dump(mode="json")
    center = SurfacePoint(1, 0, 0)
    cell = cell_at(center, 17)
    campaign = Campaign(name="microhabitat resolver", world_seed=42,
        world_profile="world_genesis_ap1_tp1_wgs2_v3",
        playable_state={"territory": {"level": 17, "world_config": world},
            "microhabitats": {"version": VERSION}})
    db.add(campaign); db.flush()
    region = Region(campaign_id=campaign.id, name="test region")
    db.add(region); db.flush()
    location = Location(region_id=region.id, name="formation", type="genesis_formation")
    db.add(location); db.flush()
    formation = GenesisNaturalFormation(id="micro-f1", campaign_id=campaign.id,
        location_id=location.id, stable_key="stable-micro-f1", archetype_id="EV-LOC-0236",
        generator_version="natural_formations_wgs2_v2", data={})
    db.add(formation); db.flush()
    e1 = SimpleNamespace(baseline={**_e1_facts(), "authority_signature": "e1-test-signature"},
                         baseline_checksum="e1-checksum")
    contract = build_contract(formation, center, 3400, {"grau_abrigado": "alto"}, e1)
    formation.data = {"microenvironment": contract}
    db.add(GenesisFormationCoverageCell(id="micro-c1", campaign_id=campaign.id,
        formation_id=formation.id, face=cell.face, level=cell.level, x=cell.x, y=cell.y,
        contract_version=COVERAGE_VERSION, contract_checksum=checksum(["coverage"])) )
    db.flush()
    inside = resolve(db, campaign.id, center)
    outside = resolve(db, campaign.id, SurfacePoint(1, 10_000, 0))
    assert inside is not None and inside["canonical_id"] == "stable-micro-f1"
    assert type(inside["modifiers"]["solar_exposure_reduction_ppm"]) is int
    assert 0 < inside["modifiers"]["solar_exposure_reduction_ppm"] <= 300_000
    assert outside is None
    db.commit(); db.expire_all(); db.info.clear()
    assert resolve(db, campaign.id, center) == inside
