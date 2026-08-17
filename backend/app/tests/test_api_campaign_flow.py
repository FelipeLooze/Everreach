def test_full_campaign_flow(client, fake_llm):
    resp = client.post("/api/campaigns", json={"name": "My Campaign"})
    assert resp.status_code == 200
    campaign = resp.json()
    campaign_id = campaign["id"]

    resp = client.post(f"/api/campaigns/{campaign_id}/characters", json={"name": "Hero"})
    assert resp.status_code == 200
    character = resp.json()
    assert character["level"] == 0
    assert character["status"] == "ALIVE"
    assert character["region_id"] is None
    assert character["location_id"] is None
    character_id = character["id"]

    resp = client.get(f"/api/campaigns/{campaign_id}/map")
    assert resp.status_code == 200
    assert resp.json() == {"regions": [], "locations": [], "connections": []}

    resp = client.get(f"/api/campaigns/{campaign_id}/quests", params={"character_id": character_id})
    assert resp.status_code == 200
    assert resp.json()["quests"] == []

    resp = client.get(f"/api/campaigns/{campaign_id}/state", params={"character_id": character_id})
    assert resp.status_code == 200
    assert resp.json()["region"] is None
    assert resp.json()["location"] is None

    resp = client.post(
        f"/api/campaigns/{campaign_id}/actions",
        params={"character_id": character_id},
        json={"text": "I look around"},
    )
    assert resp.status_code == 409

    resp = client.post(f"/api/campaigns/{campaign_id}/start", params={"character_id": character_id})
    assert resp.status_code == 200
    assert resp.json()["narrative"] == "[test narration]"
    assert resp.json()["narrator_unavailable"] is False
    assert resp.json()["state"]["location"]["name"] == "Cardal"
    assert resp.json()["state"]["opening_narrative"] == "[test narration]"
    assert resp.json()["state"]["world_time"] == {"year": 1, "month": 1, "day": 1, "hour": 8, "minute": 0}
    assert len(fake_llm.calls) == 1

    repeated_start = client.post(
        f"/api/campaigns/{campaign_id}/start", params={"character_id": character_id}
    )
    assert repeated_start.status_code == 200
    assert repeated_start.json()["narrative"] == "[test narration]"
    assert len(fake_llm.calls) == 1

    resp = client.get(f"/api/campaigns/{campaign_id}/state", params={"character_id": character_id})
    assert resp.status_code == 200
    state = resp.json()
    assert state["character"]["id"] == character_id
    assert state["opening_narrative"] == "[test narration]"
    assert state["region"]["name"] == "Vale Verdejante"
    assert state["location"]["name"] == "Cardal"

    resp = client.post(
        f"/api/campaigns/{campaign_id}/actions",
        params={"character_id": character_id},
        json={"text": "I look around the village"},
    )
    assert resp.status_code == 200
    action = resp.json()
    assert action["narrative"]
    assert action["intent_type"] == "FREEFORM"
    narrator_system, narrator_prompt = fake_llm.calls[-1]
    assert "nunca controla o protagonista" in narrator_system
    assert "PLAYER INPUT:\nI look around the village" in narrator_prompt
    assert "RECENT HISTORY:\nNARRATOR: [test narration]" in narrator_prompt

    resp = client.get(f"/api/campaigns/{campaign_id}/story", params={"character_id": character_id})
    assert resp.status_code == 200
    story = resp.json()["entries"]
    assert [entry["kind"] for entry in story] == ["narrator", "player", "narrator"]
    assert story[-2]["text"] == "I look around the village"
    assert story[-1]["text"] == action["narrative"]

    resp = client.get(f"/api/campaigns/{campaign_id}/quests", params={"character_id": character_id})
    assert resp.status_code == 200
    quests = resp.json()["quests"]
    assert len(quests) == 1
    assert quests[0]["status"] == "ACTIVE"

    resp = client.get(
        f"/api/campaigns/{campaign_id}/journal",
        params={"character_id": character_id},
    )
    assert resp.status_code == 200
    event_types = [event["event_type"] for event in resp.json()["events"]]
    assert "CHARACTER_CREATED" in event_types
    assert "WORLD_STARTED" in event_types
    assert "STORY_EXCHANGE" in event_types
    assert all(event["actor_id"] == character_id for event in resp.json()["events"])
    assert resp.json()["memories"]
    assert all(memory["source_event_id"] for memory in resp.json()["memories"])

    resp = client.get(f"/api/campaigns/{campaign_id}/map")
    assert resp.status_code == 200
    map_data = resp.json()
    assert any(r["name"] == "Vale Verdejante" for r in map_data["regions"])
    assert [location["name"] for location in map_data["locations"]] == ["Cardal"]


def test_dead_character_action_returns_409(client):
    resp = client.post("/api/campaigns", json={"name": "My Campaign"})
    campaign_id = resp.json()["id"]
    resp = client.post(f"/api/campaigns/{campaign_id}/characters", json={"name": "Hero"})
    character_id = resp.json()["id"]
    resp = client.post(f"/api/campaigns/{campaign_id}/start", params={"character_id": character_id})
    assert resp.status_code == 200

    from app.db.database import get_db
    from app.game.character.service import kill_character
    from app.main import app

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    from app.db.models.character import Character

    character = db.get(Character, character_id)
    kill_character(db, campaign_id, character)
    db.commit()

    resp = client.post(
        f"/api/campaigns/{campaign_id}/actions",
        params={"character_id": character_id},
        json={"text": "I try to stand up"},
    )
    assert resp.status_code == 409


def test_campaigns_can_be_listed_and_continued_without_calling_llm(client, fake_llm):
    older = client.post("/api/campaigns", json={"name": "Campanha Antiga"}).json()
    older_character = client.post(
        f"/api/campaigns/{older['id']}/characters", json={"name": "Veterano"}
    ).json()
    newer = client.post("/api/campaigns", json={"name": "Campanha Nova"}).json()
    newer_character = client.post(
        f"/api/campaigns/{newer['id']}/characters", json={"name": "Novato"}
    ).json()

    response = client.get("/api/campaigns")

    assert response.status_code == 200
    campaigns = response.json()
    assert [campaign["id"] for campaign in campaigns] == [newer["id"], older["id"]]
    assert campaigns[0]["characters"] == [newer_character]
    assert campaigns[1]["characters"] == [older_character]
    assert campaigns[0]["characters"][0]["region_id"] is None
    assert fake_llm.calls == []


def test_deleted_campaign_disappears_from_campaign_list(client):
    campaign = client.post("/api/campaigns", json={"name": "Temporária"}).json()
    client.post(f"/api/campaigns/{campaign['id']}/characters", json={"name": "Herói"})

    assert client.delete(f"/api/campaigns/{campaign['id']}").status_code == 200

    response = client.get("/api/campaigns")
    assert response.status_code == 200
    assert all(item["id"] != campaign["id"] for item in response.json())
