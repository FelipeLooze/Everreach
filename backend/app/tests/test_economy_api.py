from app.core.enums import NPCActivity
from app.db.models.character import Character
from app.db.models.npc import NPC


def test_economy_endpoint_exposes_only_current_location(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Economy API"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters",
        json={"name": "Logan", "earth_profession": "BLACKSMITH"},
    ).json()
    start = client.post(
        f"/api/campaigns/{campaign['id']}/start?character_id={character['id']}"
    )
    assert start.status_code == 200

    blacksmith = db_session.query(NPC).filter(
        NPC.campaign_id == campaign["id"], NPC.role == "ferreira"
    ).one()
    blacksmith.activity = NPCActivity.WORKING.value
    db_character = db_session.get(Character, character["id"])
    db_character.location_id = blacksmith.workplace_location_id
    db_session.flush()

    response = client.get(
        f"/api/campaigns/{campaign['id']}/economy?character_id={character['id']}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["balance_bronze"] == 0
    assert len(body["shops"]) == 1
    assert body["shops"][0]["operator_available"] is True
    assert any(row["name"] == "Faca de Ferro" for row in body["shops"][0]["listings"])
    assert any(job["title"] == "Ajudante de Ferreiro" for job in body["jobs"])
