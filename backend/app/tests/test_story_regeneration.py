import json

from app.ai.llm_service import DisabledLLMService
from app.api.dependencies.llm import set_role_llm_service_overrides
from app.core.enums import EventType
from app.db.models.event import WorldEvent


def _create_started_character(client):
    campaign = client.post("/api/campaigns", json={"name": "Regeneration"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters",
        json={"name": "Logan"},
    ).json()
    client.post(
        f"/api/campaigns/{campaign['id']}/start",
        params={"character_id": character["id"]},
    )
    return campaign["id"], character["id"]


def test_regeneration_replaces_only_effective_last_narrative(client, db_session, fake_llm):
    campaign_id, character_id = _create_started_character(client)
    opening_event = db_session.query(WorldEvent).filter(
        WorldEvent.event_type == EventType.WORLD_STARTED,
    ).one()
    original_payload = json.loads(opening_event.payload_json)
    original_world_minute = opening_event.world_minute

    fake_llm.generate = lambda system, prompt: "A praça permanece cheia de recém-chegados confusos."
    response = client.post(
        f"/api/campaigns/{campaign_id}/story/regenerate",
        params={"character_id": character_id},
        json={"feedback": "Deixe mais curto e sem iniciar conversa com NPCs."},
    )

    assert response.status_code == 200
    regenerated = "A praça permanece cheia de recém-chegados confusos."
    assert response.json()["entry"]["text"] == regenerated

    story = client.get(
        f"/api/campaigns/{campaign_id}/story",
        params={"character_id": character_id},
    ).json()["entries"]
    assert [entry["text"] for entry in story] == [regenerated]

    state = client.get(
        f"/api/campaigns/{campaign_id}/state",
        params={"character_id": character_id},
    ).json()
    assert state["opening_narrative"] == regenerated

    db_session.refresh(opening_event)
    assert json.loads(opening_event.payload_json) == original_payload
    assert opening_event.world_minute == original_world_minute
    revision = db_session.query(WorldEvent).filter(
        WorldEvent.event_type == EventType.STORY_REGENERATED,
    ).one()
    revision_payload = json.loads(revision.payload_json)
    assert revision_payload["target_event_id"] == opening_event.id
    assert revision_payload["feedback"] == "Deixe mais curto e sem iniciar conversa com NPCs."


def test_regeneration_requires_an_existing_narrator_message(client):
    campaign = client.post("/api/campaigns", json={"name": "Empty"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters",
        json={"name": "Logan"},
    ).json()

    response = client.post(
        f"/api/campaigns/{campaign['id']}/story/regenerate",
        params={"character_id": character["id"]},
        json={"feedback": "Mais curto."},
    )
    assert response.status_code == 409


def test_disabled_automatic_roles_do_not_call_the_configured_test_model(client, fake_llm):
    campaign_id, character_id = _create_started_character(client)
    calls_after_opening = len(fake_llm.calls)
    set_role_llm_service_overrides(
        intent=DisabledLLMService(),
        narrative=DisabledLLMService(),
    )

    response = client.post(
        f"/api/campaigns/{campaign_id}/actions",
        params={"character_id": character_id},
        json={"text": "Logan observa a praça."},
    )

    assert response.status_code == 200
    assert response.json()["intent_type"] == "FREEFORM"
    assert response.json()["narrator_unavailable"] is True
    assert len(fake_llm.calls) == calls_after_opening
