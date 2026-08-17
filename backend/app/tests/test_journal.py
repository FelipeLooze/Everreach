from app.core.enums import EventType
from app.game.character.service import create_character
from app.game.world.seed import create_campaign, seed_initial_region
from app.services.event_log import log_event


def test_journal_event_exposes_structured_payload(client, db_session):
    campaign = create_campaign(
        db_session,
        "Journal Payload",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        village.id,
    )

    log_event(
        db_session,
        campaign.id,
        EventType.TRAVEL_INCIDENT,
        actor_type="character",
        actor_id=character.id,
        payload={
            "kind": "FATIGUE",
            "extra_stamina": 2.5,
        },
    )

    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/journal",
        params={
            "character_id": character.id,
        },
    )

    assert response.status_code == 200

    data = response.json()

    incident = next(
        event
        for event in data["events"]
        if event["event_type"] == EventType.TRAVEL_INCIDENT.value
    )

    assert incident["payload"]["kind"] == "FATIGUE"
    assert incident["payload"]["extra_stamina"] == 2.5
