from app.core.enums import EventType
from app.core.enums import MemoryOwnerType
from app.db.models.memory import Memory
from app.game.world.seed import create_campaign
from app.services.event_log import log_event, recent_events


def test_log_event_persists_and_is_queryable(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    db_session.commit()

    log_event(db_session, campaign.id, EventType.PLAYER_RESTED, actor_type="character", actor_id="char_1")
    db_session.commit()

    events = recent_events(db_session, campaign.id)
    event_types = [e.event_type for e in events]
    assert EventType.CAMPAIGN_CREATED.value in event_types
    assert EventType.PLAYER_RESTED.value in event_types


def test_recent_events_respects_limit(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    for _ in range(5):
        log_event(db_session, campaign.id, EventType.PLAYER_RESTED)
    db_session.commit()

    events = recent_events(db_session, campaign.id, limit=3)
    assert len(events) == 3


def test_event_importance_creates_a_traceable_owner_memory(db_session):
    campaign = create_campaign(db_session, "Important Event")
    db_session.commit()

    event = log_event(
        db_session,
        campaign.id,
        EventType.PLAYER_LEVELED_UP,
        actor_type="character",
        actor_id="char_important",
        payload={"new_level": 1},
    )
    db_session.commit()

    memory = db_session.query(Memory).one()
    assert event.importance == 4
    assert memory.owner_type == MemoryOwnerType.PLAYER.value
    assert memory.owner_id == "char_important"
    assert memory.source_event_id == event.id
    assert memory.importance == event.importance


def test_recent_events_can_filter_actor_and_importance(db_session):
    campaign = create_campaign(db_session, "Filtered Events")
    log_event(
        db_session,
        campaign.id,
        EventType.PLAYER_RESTED,
        actor_type="character",
        actor_id="char_a",
    )
    important = log_event(
        db_session,
        campaign.id,
        EventType.PLAYER_MET_NPC,
        actor_type="character",
        actor_id="char_a",
        payload={"npc_name": "A"},
    )
    log_event(
        db_session,
        campaign.id,
        EventType.PLAYER_MET_NPC,
        actor_type="character",
        actor_id="char_b",
        payload={"npc_name": "B"},
    )
    db_session.commit()

    assert recent_events(
        db_session, campaign.id, actor_id="char_a", min_importance=3
    ) == [important]
