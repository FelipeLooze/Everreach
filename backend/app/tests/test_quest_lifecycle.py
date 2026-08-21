"""Phase 12A — Quest Lifecycle.

Establishes three previously-conflated concepts as genuinely separate:
Quest world-existence (a Quest row, independent of any character),
character participation (CharacterQuest), and the terminal states a quest
situation can resolve into — including resolving without the protagonist
ever touching it (RESOLVED_EXTERNALLY/EXPIRED/CANCELLED), which is what
lets a later phase implement "no protagonist privilege" (12H/12K) without
a schema change.

Character-level "quest awareness" distinct from participation (12J, via
the Knowledge system) is intentionally NOT implemented here — see the
QuestStatus.NOT_STARTED docstring.
"""

import pytest

from app.core.enums import EventType, QuestSource, QuestStatus
from app.db.models.quest import CharacterQuest, Quest
from app.game.character.service import create_character
from app.game.quests.service import (
    QuestLifecycleError,
    abandon_quest,
    cancel_quest,
    create_quest,
    expire_quest,
    fail_quest,
    resolve_quest_externally,
    start_quest,
)
from app.game.world.seed import create_campaign, seed_initial_region
from app.services.event_log import recent_events


def _setup(db_session):
    campaign = create_campaign(db_session, "Quest Lifecycle")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, character


def test_create_quest_exists_independent_of_any_character(db_session):
    campaign, region, character = _setup(db_session)

    quest = create_quest(
        db_session,
        region.id,
        "Cabras desaparecidas",
        "Três cabras sumiram ao norte de Cardal.",
        source=QuestSource.NPC_REQUEST,
        objectives=["Encontrar as cabras."],
    )

    assert quest.status == QuestStatus.AVAILABLE
    assert quest.source == QuestSource.NPC_REQUEST
    assert (
        db_session.query(CharacterQuest)
        .filter(CharacterQuest.quest_id == quest.id)
        .count()
        == 0
    )


def test_quest_without_explicit_source_defaults_to_self_discovered(db_session):
    campaign, region, character = _setup(db_session)
    quest = Quest(region_id=region.id, name="Achado no caminho", description="")
    db_session.add(quest)
    db_session.flush()

    assert quest.status == QuestStatus.AVAILABLE
    assert quest.source == QuestSource.SELF_DISCOVERED


def test_start_quest_creates_active_participation(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(
        db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST
    )

    cq = start_quest(db_session, character.id, quest.id)

    assert cq.status == QuestStatus.ACTIVE
    events = recent_events(db_session, campaign.id)
    assert any(e.event_type == EventType.QUEST_STARTED for e in events)


def test_start_quest_is_idempotent(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)

    first = start_quest(db_session, character.id, quest.id)
    second = start_quest(db_session, character.id, quest.id)

    assert first.id == second.id


def test_cannot_start_a_quest_already_resolved_externally(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Cabras", source=QuestSource.NPC_REQUEST)
    resolve_quest_externally(db_session, campaign.id, quest.id, note="Outro viajante resolveu.")

    with pytest.raises(QuestLifecycleError):
        start_quest(db_session, character.id, quest.id)


def test_cannot_start_an_unknown_quest(db_session):
    campaign, region, character = _setup(db_session)

    with pytest.raises(QuestLifecycleError):
        start_quest(db_session, character.id, "quest_nonexistent")


def test_abandon_quest_marks_participation_cancelled(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)
    start_quest(db_session, character.id, quest.id)

    cq = abandon_quest(db_session, campaign.id, character.id, quest.id)

    assert cq.status == QuestStatus.CANCELLED
    events = recent_events(db_session, campaign.id)
    assert any(e.event_type == EventType.QUEST_CANCELLED for e in events)
    # The world-level Quest itself is untouched by a single character quitting.
    assert db_session.get(Quest, quest.id).status == QuestStatus.AVAILABLE


def test_cannot_abandon_a_quest_never_started(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)

    with pytest.raises(QuestLifecycleError):
        abandon_quest(db_session, campaign.id, character.id, quest.id)


def test_cannot_abandon_an_already_completed_quest(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)
    cq = start_quest(db_session, character.id, quest.id)
    cq.status = QuestStatus.COMPLETED
    db_session.flush()

    with pytest.raises(QuestLifecycleError):
        abandon_quest(db_session, campaign.id, character.id, quest.id)


def test_fail_quest_marks_participation_failed_with_reason(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)
    start_quest(db_session, character.id, quest.id)

    cq = fail_quest(db_session, campaign.id, character.id, quest.id, reason="O alvo morreu.")

    assert cq.status == QuestStatus.FAILED
    events = recent_events(db_session, campaign.id)
    failed = [e for e in events if e.event_type == EventType.QUEST_FAILED]
    assert failed and "morreu" in failed[0].payload_json


def test_resolve_quest_externally_blocks_future_participation(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Cabras", source=QuestSource.NPC_REQUEST)

    resolved = resolve_quest_externally(
        db_session, campaign.id, quest.id, note="Outro transportado já devolveu as cabras."
    )

    assert resolved.status == QuestStatus.RESOLVED_EXTERNALLY
    events = recent_events(db_session, campaign.id)
    assert any(e.event_type == EventType.QUEST_RESOLVED_EXTERNALLY for e in events)


def test_expire_and_cancel_quest_are_world_level_terminal_states(db_session):
    campaign, region, character = _setup(db_session)
    expiring = create_quest(db_session, region.id, "Caravana", source=QuestSource.NPC_REQUEST)
    cancelling = create_quest(db_session, region.id, "Encomenda", source=QuestSource.NPC_REQUEST)

    expired = expire_quest(db_session, campaign.id, expiring.id)
    cancelled = cancel_quest(db_session, campaign.id, cancelling.id, reason="Solicitante desistiu.")

    assert expired.status == QuestStatus.EXPIRED
    assert cancelled.status == QuestStatus.CANCELLED


def test_cannot_transition_a_quest_twice(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Caravana", source=QuestSource.NPC_REQUEST)
    expire_quest(db_session, campaign.id, quest.id)

    with pytest.raises(QuestLifecycleError):
        cancel_quest(db_session, campaign.id, quest.id)
