"""WGS2.4 facts are bounded catalog/physical inputs, never invented resources."""
import pytest

from app.game.world.genesis.local_formations import catalog
from app.game.world.genesis.wgs2_families import EXISTING, SUPPORTED, eligibility
from app.game.world.genesis.wgs2_identity import CLUES, VERSION, facts
from app.schemas.campaign import CampaignCreateRequest


def test_v5_profile_opt_in_and_catalog_matrix():
    assert CampaignCreateRequest(name="Variety", world_seed=42,
        world_profile="world_genesis_ap1_tp1_wgs2_v5").world_profile.endswith("v5")
    rows = catalog()
    assert len(EXISTING) == 5 and len(SUPPORTED) == 15
    assert len(set(EXISTING + SUPPORTED)) == 20
    assert set(CLUES) == set(SUPPORTED)
    assert all(item in rows for item in EXISTING + SUPPORTED)
    assert all("{direction}" in value and "EV-LOC-" not in value for value in CLUES.values())


@pytest.mark.parametrize("archetype", ["EV-LOC-0033", "EV-LOC-0036", "EV-LOC-0051", "EV-LOC-0082", "EV-LOC-0023"])
def test_identity_exposes_catalog_geometry_and_only_confirmed_physics(archetype):
    row = catalog()[archetype]
    variations = {key: values["valores_candidatos"][0]
                  for key, values in row["variacoes_procedurais"]["eixos"].items()}
    dimensions = {"horizontal_span_m": 300, "orientation_degrees": 87}
    decision = {"context": {"height_mm": 125000, "slope_ppm": 12000,
        "reference_ocean_H1": False, "E1_signature": "confirmed"}}
    result = facts(archetype, row, dimensions, variations, decision,
                   interior=archetype == "EV-LOC-0051")
    assert result["version"] == VERSION
    assert result["observable_visual"]
    if archetype == "EV-LOC-0023":
        assert "vegetação" not in result["observable_visual"]
    assert result["geometry_type"] == row["geometria"]["tipo_espacial"]
    assert result["confirmed_physical"]["T1_slope_ppm"] == 12000
    assert result["confirmed_physical"]["E1_signature"] == "confirmed"
    assert "J1_substrates" not in result["confirmed_physical"]
    assert result["resources_unconfirmed"] and result["surface_materials_unconfirmed"]
    assert result["interior_authorized"] == (archetype == "EV-LOC-0051")


def test_pending_wet_cavity_stays_blocked_without_confirmed_moisture():
    land = {"physical_inputs": {"T1_height_mm": 125000,
        "T1_slope_ppm": 12000, "reference_ocean_H1": False},
        "flora_contract": {"eligible_habitat_ids": []}}
    assert eligibility("EV-LOC-0049", land, 0)[1] == "pending"
    assert eligibility("EV-LOC-0051", land, 0)[0]


def test_four_real_evidence_sites_materialize_across_four_families(db_session, monkeypatch):
    from app.db.models.campaign import Campaign
    from app.db.models.location import Location, LocationConnection, CharacterLocationDiscovery
    from app.db.models.region import Region
    from app.db.models.world_genesis import GenesisWorld
    from app.db.models.world_natural_formations import GenesisNaturalFormation
    from app.game.character.service import create_character
    from app.game.world.genesis import local_formations
    from app.game.world.genesis.sphere_topology import CellKey, cell_center
    from app.game.world.genesis.territory import validate_travel
    from app.game.world.genesis.vegetation.microhabitat import ORIGIN_LOOKUP_VERSION, VERSION as MICRO_VERSION
    from app.game.world.genesis.vegetation.microhabitat_canonical import RESOLUTION_VERSION
    from scripts.prove_vegetation import prepare
    from scripts.validate_vegetation import inputs_vg1

    db = db_session
    sources = inputs_vg1(42)
    cid = prepare(db, sources)
    campaign = db.get(Campaign, cid)
    world = db.get(GenesisWorld, cid)
    campaign.world_profile = "world_genesis_ap1_tp1_wgs2_v5"
    sites = {
        (0, 17, 100000, 30000): "EV-LOC-0037",  # rock relief
        (0, 17, 100010, 30000): "EV-LOC-0051",  # natural cavity
        (0, 17, 100020, 30000): "EV-LOC-0082",  # arid landscape
        (0, 17, 120000, 120000): "EV-LOC-0023", # open landscape
    }
    monkeypatch.setattr("app.game.world.genesis.wgs2_families.candidate",
        lambda seed, address, records, **kw: sites.get(tuple(address[k] for k in ("face","level","x","y"))))
    region = Region(campaign_id=cid, name="controlled real sites")
    db.add(region); db.flush()
    campaign.playable_state = {
        "natural_formations": {"version":"natural_formations_wgs2_v2",
                               "selection_policy":"wgs2-family-opportunities-r1"},
        "microhabitats": {"version":MICRO_VERSION,
                           "origin_lookup_version":ORIGIN_LOOKUP_VERSION,
                           "canonical_resolution_version":RESOLUTION_VERSION},
        "territory": {"version":"territory_tp1", "level":17,
                      "world_config":world.config},
    }
    actor = create_character(db, cid, "Explorer", None, None)
    focuses = set()
    for coords, archetype in sites.items():
        cell = CellKey(*coords)
        point = cell_center(cell)
        baseline = sources.environment.sample(point)
        assert eligibility(archetype, baseline, world.config["sea_level_m"])[0]
        exterior = Location(region_id=region.id, name="known field", type="genesis_field",
            genesis_site={"version":"territory_tp1", "cell":vars(cell),
                          "point":list(point.xyz), "prepared":True})
        db.add(exterior); db.flush()
        instance = local_formations.materialize_for_site(db, campaign, exterior, _skip_origin_lookup=True)
        assert instance.archetype_id == archetype
        assert instance.data["identity"]["version"] == VERSION
        assert local_formations.materialize_for_site(db, campaign, exterior, _skip_origin_lookup=True).id == instance.id
        actor.location_id = instance.location_id
        observed = local_formations.inspect_current(db, actor.id)
        investigated = local_formations.interact_current(db, actor.id)
        assert observed["identity"]["archetype_id"] == archetype
        assert investigated["investigated"]["geometry_type"] == catalog()[archetype]["geometria"]["tipo_espacial"]
        focuses.add(investigated["investigated"]["focus"])
        assert "indicio proximo" not in observed["known_accesses"]
        assert db.query(LocationConnection).filter_by(from_location_id=instance.location_id).count() >= 1
        if archetype in ("EV-LOC-0023", "EV-LOC-0082"):
            subarea_id = instance.data["subarea_location_ids"][0]
            route = db.query(LocationConnection).filter_by(
                from_location_id=instance.location_id, to_location_id=subarea_id).one()
            validate_travel(db, cid, route)
            actor.location_id = subarea_id
            subarea_observation = local_formations.inspect_current(db, actor.id)
            assert subarea_observation["instance_id"] == instance.id
            assert subarea_observation["features"] != observed["features"]
            back = db.query(LocationConnection).filter_by(
                from_location_id=subarea_id, to_location_id=instance.location_id).one()
            validate_travel(db, cid, back)
        if archetype == "EV-LOC-0051":
            assert instance.data["interior_location_id"]
            assert instance.data["dimensions"]["vertical_span_m"] == instance.data["variations"]["altura_teto_m"]
            actor.location_id = instance.data["interior_location_id"]
            assert local_formations.inspect_current(db, actor.id)["known_accesses"] == []
            from app.game.discovery.service import discover_connection
            exit_edge = db.query(LocationConnection).filter_by(
                from_location_id=actor.location_id, direction="sair").one()
            discover_connection(db, actor.id, exit_edge.id)
            assert "sair" in local_formations.inspect_current(db, actor.id)["known_accesses"]
    assert db.query(GenesisNaturalFormation).filter_by(campaign_id=cid).count() == 4
    assert len(focuses) == 4
    assert db.query(CharacterLocationDiscovery).count() == 0
    db.commit(); db.expire_all()
    assert db.query(GenesisNaturalFormation).filter_by(campaign_id=cid).count() == 4
