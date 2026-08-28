"""S1.5: Map View is the canonical map read projection."""

from app.game.character.service import create_character
from app.game.discovery.service import record_location_visit
from app.game.world.seed import create_campaign, seed_initial_region


def test_legacy_map_is_a_compatible_projection_of_map_view(client, db_session):
    campaign = create_campaign(db_session, "Consolidated Map")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Cartographer", region.id, village.id)
    record_location_visit(db_session, character.id, village.id, source="test")
    db_session.commit()

    query = f"character_id={character.id}"
    canonical_response = client.get(f"/api/campaigns/{campaign.id}/map-view?{query}")
    legacy_response = client.get(f"/api/campaigns/{campaign.id}/map?{query}")

    assert canonical_response.status_code == 200
    assert legacy_response.status_code == 200
    canonical = canonical_response.json()
    legacy = legacy_response.json()

    assert legacy["regions"] == [
        {
            "id": entry["id"],
            "name": entry["name"],
            "description": None,
            "discovery_status": entry["discovery_status"],
        }
        for entry in canonical["regions"]
    ]
    assert legacy["locations"] == [
        {
            "id": entry["id"],
            "region_id": entry["region_id"],
            "name": entry["name"],
            "type": entry["type"],
            "x": entry["x"],
            "y": entry["y"],
            "discovery_status": entry["discovery_status"],
        }
        for entry in canonical["locations"]
    ]
    assert legacy["connections"] == canonical["routes"]


def test_legacy_map_is_marked_deprecated_in_openapi(client):
    operation = client.get("/openapi.json").json()["paths"]["/api/campaigns/{campaign_id}/map"]["get"]
    assert operation["deprecated"] is True
