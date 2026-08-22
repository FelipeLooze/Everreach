from app.db.models.campaign import Campaign, WorldTime
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.db.models.knowledge_index import IndexedKnowledgeDocument
from app.db.models.npc import NPC
from app.db.models.region import Region
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.memory import Memory
from app.db.models.relationship import CharacterNPCRelationship


def _create_started_campaign(client, campaign_name: str, character_name: str):
    campaign = client.post("/api/campaigns", json={"name": campaign_name}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": character_name}
    ).json()
    response = client.post(
        f"/api/campaigns/{campaign['id']}/start", params={"character_id": character["id"]}
    )
    assert response.status_code == 200
    return campaign, character


def test_reset_deletes_only_the_selected_campaign(client, db_session):
    deleted_campaign, deleted_character = _create_started_campaign(client, "Apagar", "Primeiro")
    kept_campaign, kept_character = _create_started_campaign(client, "Preservar", "Segundo")

    response = client.delete(f"/api/campaigns/{deleted_campaign['id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    db_session.expire_all()
    assert db_session.get(Campaign, deleted_campaign["id"]) is None
    assert db_session.get(Character, deleted_character["id"]) is None
    assert db_session.query(Region).filter(Region.campaign_id == deleted_campaign["id"]).count() == 0
    assert db_session.query(WorldTime).filter(WorldTime.campaign_id == deleted_campaign["id"]).count() == 0
    assert db_session.query(WorldEvent).filter(WorldEvent.campaign_id == deleted_campaign["id"]).count() == 0
    assert db_session.query(Memory).filter(Memory.campaign_id == deleted_campaign["id"]).count() == 0
    assert (
        db_session.query(IndexedKnowledgeDocument)
        .filter(IndexedKnowledgeDocument.campaign_id == deleted_campaign["id"])
        .count()
        == 0
    )
    assert (
        db_session.query(CharacterNPCRelationship)
        .filter(CharacterNPCRelationship.campaign_id == deleted_campaign["id"])
        .count()
        == 0
    )
    assert db_session.query(NPC).filter(NPC.campaign_id == deleted_campaign["id"]).count() == 0
    assert (
        db_session.query(SimulatedPlayer)
        .filter(SimulatedPlayer.campaign_id == deleted_campaign["id"])
        .count()
        == 0
    )

    assert db_session.get(Campaign, kept_campaign["id"]) is not None
    assert db_session.get(Character, kept_character["id"]) is not None
    assert client.get(f"/api/campaigns/{kept_campaign['id']}").status_code == 200
    assert client.get(f"/api/campaigns/{deleted_campaign['id']}").status_code == 404


def test_reset_unknown_campaign_returns_404(client):
    response = client.delete("/api/campaigns/campaign_inexistente")
    assert response.status_code == 404
