"""Phase 12D — Failure.

A quest does not stay frozen just because the protagonist isn't
interacting with it. A Quest may carry an opportunity-window deadline
(world-level: nobody claimed it in time) and a CharacterQuest may
separately carry a deadline for one character's active participation.
Both are optional — most quests have none.
"""

from app.core.enums import QuestSource, QuestStatus
from app.db.models.quest import CharacterQuest, Quest
from app.game.character.service import create_character
from app.game.quests.service import check_deadlines, create_quest, fail_quest, start_quest
from app.game.time.clock import advance_world_time, get_world_time
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Quest Failure")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, character


def test_quest_without_a_deadline_is_unaffected_by_time_passing(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Sem prazo", source=QuestSource.NPC_REQUEST)

    advance_world_time(db_session, campaign.id, 60 * 24 * 30)
    check_deadlines(db_session, campaign.id, character.id)

    assert db_session.get(Quest, quest.id).status == QuestStatus.AVAILABLE


def test_available_quest_expires_once_its_deadline_passes(db_session):
    campaign, region, character = _setup(db_session)
    now = get_world_time(db_session, campaign.id).total_minutes()
    quest = create_quest(
        db_session, region.id, "Caravana parte em breve",
        source=QuestSource.NPC_REQUEST, deadline_world_minute=now + 60,
    )

    advance_world_time(db_session, campaign.id, 30)
    check_deadlines(db_session, campaign.id, character.id)
    assert db_session.get(Quest, quest.id).status == QuestStatus.AVAILABLE

    advance_world_time(db_session, campaign.id, 60)
    check_deadlines(db_session, campaign.id, character.id)
    assert db_session.get(Quest, quest.id).status == QuestStatus.EXPIRED


def test_started_quest_is_not_affected_by_its_own_expired_world_level_deadline(db_session):
    campaign, region, character = _setup(db_session)
    now = get_world_time(db_session, campaign.id).total_minutes()
    quest = create_quest(
        db_session, region.id, "Aceita a tempo",
        source=QuestSource.NPC_REQUEST, deadline_world_minute=now + 60,
    )
    start_quest(db_session, character.id, quest.id)

    advance_world_time(db_session, campaign.id, 120)
    check_deadlines(db_session, campaign.id, character.id)

    # The world-level Quest itself has no participation deadline check —
    # once claimed, the opportunity-window deadline no longer applies to
    # a Quest already AVAILABLE=false (it was already ACTIVE-only via the
    # CharacterQuest). Quest.status should remain AVAILABLE since nothing
    # ever transitioned it away (start_quest doesn't change Quest.status).
    assert db_session.get(Quest, quest.id).status == QuestStatus.AVAILABLE
    cq = (
        db_session.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character.id, CharacterQuest.quest_id == quest.id)
        .first()
    )
    assert cq.status == QuestStatus.ACTIVE


def test_character_participation_fails_once_its_own_deadline_passes(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Resgate urgente", source=QuestSource.NPC_REQUEST)
    now = get_world_time(db_session, campaign.id).total_minutes()
    start_quest(db_session, character.id, quest.id, deadline_world_minute=now + 60)

    advance_world_time(db_session, campaign.id, 90)
    check_deadlines(db_session, campaign.id, character.id)

    cq = (
        db_session.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character.id, CharacterQuest.quest_id == quest.id)
        .first()
    )
    assert cq.status == QuestStatus.FAILED


def test_check_deadlines_without_character_id_only_checks_world_level(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Cabras", source=QuestSource.NPC_REQUEST)
    now = get_world_time(db_session, campaign.id).total_minutes()
    start_quest(db_session, character.id, quest.id, deadline_world_minute=now + 30)

    advance_world_time(db_session, campaign.id, 90)
    check_deadlines(db_session, campaign.id)

    cq = (
        db_session.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character.id, CharacterQuest.quest_id == quest.id)
        .first()
    )
    assert cq.status == QuestStatus.ACTIVE


def test_check_deadlines_is_idempotent(db_session):
    campaign, region, character = _setup(db_session)
    now = get_world_time(db_session, campaign.id).total_minutes()
    quest = create_quest(
        db_session, region.id, "Caravana", source=QuestSource.NPC_REQUEST,
        deadline_world_minute=now + 10,
    )
    advance_world_time(db_session, campaign.id, 20)

    check_deadlines(db_session, campaign.id, character.id)
    check_deadlines(db_session, campaign.id, character.id)

    assert db_session.get(Quest, quest.id).status == QuestStatus.EXPIRED
