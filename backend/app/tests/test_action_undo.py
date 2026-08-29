import json

from app.core.enums import EventType, ItemType
from app.db.models.action_checkpoint import ActionCheckpoint
from app.db.models.event import WorldEvent
from app.game.inventory.service import add_item, get_or_create_item


def _started_character(client):
    campaign = client.post("/api/campaigns", json={"name": "Undo"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters",
        json={"name": "Logan"},
    ).json()
    client.post(
        f"/api/campaigns/{campaign['id']}/start",
        params={"character_id": character["id"]},
    )
    return campaign["id"], character["id"]


def test_undo_restores_inventory_time_and_story_without_replaying_action(
    client, db_session, fake_llm
):
    campaign_id, character_id = _started_character(client)
    get_or_create_item(db_session, "Pedra de teste", ItemType.MISC.value)
    item = add_item(db_session, character_id, "Pedra de teste")
    db_session.commit()
    state_before = client.get(
        f"/api/campaigns/{campaign_id}/state",
        params={"character_id": character_id},
    ).json()
    story_before = client.get(
        f"/api/campaigns/{campaign_id}/story",
        params={"character_id": character_id},
    ).json()

    def generate(system: str, prompt: str) -> str:
        fake_llm.calls.append((system, prompt))
        if "intent" in system.lower():
            return json.dumps({"intent": "DROP", "target": "Pedra de teste"})
        return "Logan deixa a pedra no chão."

    fake_llm.generate = generate
    action = client.post(
        f"/api/campaigns/{campaign_id}/actions",
        params={"character_id": character_id},
        json={"text": "Deixar a pedra no chão", "action_key": "drop-stone"},
    )
    assert action.status_code == 200
    db_session.refresh(item)
    assert item.location_type == "WORLD_LOCATION"

    status = client.get(
        f"/api/campaigns/{campaign_id}/actions/undo-status",
        params={"character_id": character_id},
    )
    assert status.status_code == 200
    assert status.json()["available"] is True
    assert status.json()["action_text"] == "Deixar a pedra no chão"

    undone = client.post(
        f"/api/campaigns/{campaign_id}/actions/undo-last",
        params={"character_id": character_id},
        json={"reason": "A ação não deveria retirar o item do inventário."},
    )
    assert undone.status_code == 200
    assert undone.json()["state"]["world_time"] == state_before["world_time"]
    assert any(
        entry["item_instance_id"] == item.id
        for entry in undone.json()["state"]["inventory"]["items"]
    )
    assert client.get(
        f"/api/campaigns/{campaign_id}/story",
        params={"character_id": character_id},
    ).json() == story_before

    checkpoint = db_session.query(ActionCheckpoint).one()
    assert checkpoint.status == "UNDONE"
    undo_event = db_session.query(WorldEvent).filter(
        WorldEvent.event_type == EventType.ACTION_UNDONE,
    ).one()
    payload = json.loads(undo_event.payload_json)
    assert payload["action_key"] == "drop-stone"
    assert payload["reason"] == "A ação não deveria retirar o item do inventário."
    assert db_session.query(WorldEvent).filter(
        WorldEvent.event_type == EventType.STORY_EXCHANGE,
    ).count() == 0


def test_regeneration_does_not_invalidate_mechanical_undo(client, fake_llm):
    campaign_id, character_id = _started_character(client)
    client.post(
        f"/api/campaigns/{campaign_id}/actions",
        params={"character_id": character_id},
        json={"text": "Olhar ao redor", "action_key": "look-once"},
    )
    regenerated = client.post(
        f"/api/campaigns/{campaign_id}/story/regenerate",
        params={"character_id": character_id},
        json={"feedback": "Não realize ações pelo protagonista."},
    )
    assert regenerated.status_code == 200

    status = client.get(
        f"/api/campaigns/{campaign_id}/actions/undo-status",
        params={"character_id": character_id},
    )
    assert status.json()["available"] is True


def test_undo_is_rejected_after_an_unrelated_persistent_change(client, db_session):
    campaign_id, character_id = _started_character(client)
    client.post(
        f"/api/campaigns/{campaign_id}/actions",
        params={"character_id": character_id},
        json={"text": "Esperar um instante", "action_key": "wait-once"},
    )
    db_session.add(
        WorldEvent(
            campaign_id=campaign_id,
            event_type="EXTERNAL_CHANGE",
            actor_type="character",
            actor_id=character_id,
            payload_json="{}",
        )
    )
    db_session.commit()

    status = client.get(
        f"/api/campaigns/{campaign_id}/actions/undo-status",
        params={"character_id": character_id},
    )
    assert status.json() == {
        "available": False,
        "action_text": None,
        "mechanical_summary": None,
    }
    response = client.post(
        f"/api/campaigns/{campaign_id}/actions/undo-last",
        params={"character_id": character_id},
        json={"reason": "Tentar voltar."},
    )
    assert response.status_code == 409


def test_deleting_campaign_removes_its_action_checkpoints(client, db_session):
    campaign_id, character_id = _started_character(client)
    client.post(
        f"/api/campaigns/{campaign_id}/actions",
        params={"character_id": character_id},
        json={"text": "Olhar ao redor", "action_key": "before-delete"},
    )
    assert db_session.query(ActionCheckpoint).count() == 1

    response = client.delete(f"/api/campaigns/{campaign_id}")
    assert response.status_code == 200
    assert db_session.query(ActionCheckpoint).count() == 0
