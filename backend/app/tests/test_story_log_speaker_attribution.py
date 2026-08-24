"""Phase 24D — Conversation & Speaker State.

get_recent_story_log/_entries_from_events now carries npc_id/npc_name
through from the STORY_EXCHANGE payload onto StoryEntry, so a later turn's
history framing can attribute a past narrated response to the specific
NPC the backend already resolved as active for it (see engine.py's
context_npc) instead of a generic "the narrator said" label. These tests
exercise that persistence path directly, independent of build_recent_history.
"""
from app.core.enums import EventType
from app.game.character.service import create_character
from app.game.world.seed import create_campaign, seed_initial_region
from app.services.event_log import log_event
from app.services.story_log import (
    SPEAKER_NARRATOR,
    SPEAKER_PLAYER,
    get_recent_story_log,
)


def _setup(db_session):
    campaign = create_campaign(db_session, "Story Log Test")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()
    return campaign, character


def test_story_exchange_with_npc_carries_npc_id_and_name_onto_entry(db_session):
    campaign, character = _setup(db_session)
    log_event(
        db_session,
        campaign.id,
        EventType.STORY_EXCHANGE,
        actor_type="character",
        actor_id=character.id,
        payload={
            "player_text": "Qual o seu nome?",
            "narrative": "— Sou Aldric — diz o ancião.",
            "npc_id": "npc_abc123",
            "npc_name": "Aldric",
        },
    )
    db_session.commit()

    entries = get_recent_story_log(db_session, campaign.id, character.id)
    narrator_entries = [e for e in entries if e.kind == SPEAKER_NARRATOR]

    assert len(narrator_entries) == 1
    assert narrator_entries[0].npc_id == "npc_abc123"
    assert narrator_entries[0].npc_name == "Aldric"


def test_story_exchange_without_npc_leaves_attribution_none(db_session):
    campaign, character = _setup(db_session)
    log_event(
        db_session,
        campaign.id,
        EventType.STORY_EXCHANGE,
        actor_type="character",
        actor_id=character.id,
        payload={
            "player_text": "Olhar ao redor",
            "narrative": "Nada acontece de imediato.",
        },
    )
    db_session.commit()

    entries = get_recent_story_log(db_session, campaign.id, character.id)
    narrator_entries = [e for e in entries if e.kind == SPEAKER_NARRATOR]

    assert len(narrator_entries) == 1
    assert narrator_entries[0].npc_id is None
    assert narrator_entries[0].npc_name is None


def test_player_entries_never_carry_npc_attribution(db_session):
    campaign, character = _setup(db_session)
    log_event(
        db_session,
        campaign.id,
        EventType.STORY_EXCHANGE,
        actor_type="character",
        actor_id=character.id,
        payload={
            "player_text": "Qual o seu nome?",
            "narrative": "— Sou Aldric — diz o ancião.",
            "npc_id": "npc_abc123",
            "npc_name": "Aldric",
        },
    )
    db_session.commit()

    entries = get_recent_story_log(db_session, campaign.id, character.id)
    player_entries = [e for e in entries if e.kind == SPEAKER_PLAYER]

    assert len(player_entries) == 1
    assert player_entries[0].npc_id is None
    assert player_entries[0].npc_name is None


def test_pre_phase_24d_events_without_payload_keys_degrade_to_none(db_session):
    # An event logged before this phase existed has no "npc_id"/"npc_name"
    # keys in its payload_json at all (not even null) — .get() must not
    # raise, and the resulting entry must look identical to the "no active
    # NPC" case above rather than erroring or fabricating a value.
    campaign, character = _setup(db_session)
    log_event(
        db_session,
        campaign.id,
        EventType.STORY_EXCHANGE,
        actor_type="character",
        actor_id=character.id,
        payload={
            "player_text": "Olá.",
            "narrative": "— Olá — diz alguém.",
        },
    )
    db_session.commit()

    entries = get_recent_story_log(db_session, campaign.id, character.id)
    narrator_entries = [e for e in entries if e.kind == SPEAKER_NARRATOR]

    assert narrator_entries[0].npc_id is None
    assert narrator_entries[0].npc_name is None
