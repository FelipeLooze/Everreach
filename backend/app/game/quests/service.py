from typing import Sequence

from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    ObjectiveTriggerType,
    QuestParticipationType,
    QuestSource,
    QuestStatus,
)
from app.db.models.quest import (
    CharacterQuest,
    CharacterQuestObjective,
    Quest,
    QuestObjective,
)
from app.db.models.character import Character
from app.db.models.knowledge import KnowledgeFact
from app.db.models.region import Region
from app.game.quests.consequences import QuestConsequences, apply_quest_consequences
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


def quest_existence_fact_key(quest_id: str) -> str:
    """The Knowledge fact_key (Phase 12J) registered for a Quest's mere
    existence — separate from any objective/mechanical detail about it.
    Shared with app.game.quests.discovery so the two never drift."""
    return f"quest:{quest_id}:exists"


class QuestLifecycleError(Exception):
    """An invalid Quest/CharacterQuest state transition was attempted."""


def create_quest(
    db: Session,
    region_id: str,
    name: str,
    description: str = "",
    *,
    source: QuestSource,
    objectives: Sequence[str] = (),
    deadline_world_minute: int | None = None,
    participation_type: QuestParticipationType = QuestParticipationType.OPEN,
    capacity: int | None = None,
) -> Quest:
    """The one authoritative way a Quest situation comes to exist in the
    world. Existence here is independent of any character's awareness or
    participation — nothing here creates a CharacterQuest row.

    deadline_world_minute (Phase 12D) is optional and about the
    opportunity itself expiring unclaimed (e.g. a caravan leaving) — not
    every quest needs one; see check_deadlines.

    participation_type (Phase 12K) defaults to OPEN — unlimited
    simultaneous participants, the behavior every quest already had
    before this field existed. capacity is only meaningful for LIMITED
    (and required there — a limited quest must state its limit); see
    start_quest for how it's enforced.

    Also registers the Quest's mere existence as a Knowledge fact (Phase
    12J) — a fact that is TRUE in the world the moment it happens, wholly
    separate from whether any character has actually learned it yet (see
    app.game.quests.discovery). The statement is exactly the same
    player-facing name/description Phase 12G already locked down as safe
    to expose — no hidden mechanical data leaks through this."""
    if participation_type == QuestParticipationType.LIMITED and not capacity:
        raise QuestLifecycleError("Uma missão LIMITED precisa declarar sua capacidade.")
    quest = Quest(
        region_id=region_id,
        name=name,
        description=description,
        source=source,
        deadline_world_minute=deadline_world_minute,
        participation_type=participation_type,
        capacity=capacity,
    )
    db.add(quest)
    db.flush()
    for index, objective_description in enumerate(objectives):
        db.add(QuestObjective(quest_id=quest.id, description=objective_description, order=index))
    if objectives:
        db.flush()

    region = db.get(Region, region_id)
    if region is not None:
        db.add(
            KnowledgeFact(
                campaign_id=region.campaign_id,
                subject=f"quest:{quest.id}",
                fact_key=quest_existence_fact_key(quest.id),
                statement=f"{name}: {description}" if description else name,
            )
        )
        db.flush()
    return quest


def start_quest(
    db: Session, character_id: str, quest_id: str, *, deadline_world_minute: int | None = None
) -> CharacterQuest:
    existing = (
        db.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character_id, CharacterQuest.quest_id == quest_id)
        .first()
    )
    if existing:
        return existing

    quest = db.get(Quest, quest_id)
    if quest is None:
        raise QuestLifecycleError(f"Missão desconhecida: {quest_id}")
    if quest.status != QuestStatus.AVAILABLE:
        raise QuestLifecycleError(
            f"'{quest.name}' não está mais disponível ({quest.status})."
        )

    # Phase 12K: OPEN/OFFICIAL_BOUNTY have no participant limit — the
    # behavior every quest already had. CLAIMABLE (capacity 1) and
    # LIMITED (explicit capacity) reject a new participant once already
    # at capacity — someone else got there, or there simply isn't room.
    if quest.participation_type in (
        QuestParticipationType.CLAIMABLE,
        QuestParticipationType.LIMITED,
    ):
        capacity = 1 if quest.participation_type == QuestParticipationType.CLAIMABLE else quest.capacity
        active_count = (
            db.query(CharacterQuest)
            .filter(CharacterQuest.quest_id == quest_id, CharacterQuest.status == QuestStatus.ACTIVE)
            .count()
        )
        if active_count >= capacity:
            raise QuestLifecycleError(
                f"'{quest.name}' já atingiu sua capacidade de participantes ({capacity})."
            )

    cq = CharacterQuest(
        character_id=character_id,
        quest_id=quest_id,
        status=QuestStatus.ACTIVE,
        deadline_world_minute=deadline_world_minute,
    )
    db.add(cq)
    db.flush()
    character = db.get(Character, character_id)
    if character is not None:
        log_event(
            db,
            character.campaign_id,
            EventType.QUEST_STARTED,
            actor_type="character",
            actor_id=character_id,
            payload={"quest_id": quest_id},
        )
    return cq


def _get_character_quest(db: Session, character_id: str, quest_id: str) -> CharacterQuest:
    cq = (
        db.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character_id, CharacterQuest.quest_id == quest_id)
        .first()
    )
    if cq is None:
        raise QuestLifecycleError(
            f"Personagem {character_id} não está participando da missão {quest_id}."
        )
    return cq


def abandon_quest(
    db: Session,
    campaign_id: str,
    character_id: str,
    quest_id: str,
    *,
    consequences: QuestConsequences | None = None,
) -> CharacterQuest:
    """Player-initiated withdrawal from a quest they are actively pursuing.
    Only a real, active involvement can be abandoned — a quest that already
    resolved one way or another is history, not something to undo.

    consequences (Phase 12E) is optional — most abandonments (e.g. simple
    test scaffolding) have none; a requester noticing they were left
    hanging is a real possible consequence once content actually supplies
    one."""
    cq = _get_character_quest(db, character_id, quest_id)
    if cq.status != QuestStatus.ACTIVE:
        raise QuestLifecycleError(
            f"Não é possível abandonar uma missão com status {cq.status}."
        )
    cq.status = QuestStatus.CANCELLED
    db.flush()
    log_event(
        db,
        campaign_id,
        EventType.QUEST_CANCELLED,
        actor_type="character",
        actor_id=character_id,
        payload={"quest_id": quest_id},
    )
    apply_quest_consequences(db, campaign_id, character_id, consequences)
    return cq


def fail_quest(
    db: Session,
    campaign_id: str,
    character_id: str,
    quest_id: str,
    *,
    reason: str = "",
    consequences: QuestConsequences | None = None,
) -> CharacterQuest:
    """System-initiated failure of one character's participation (e.g. a
    deadline passed, a target died) — see Phase 12D. This only closes that
    character's involvement; the world-level Quest is untouched, since
    someone else may still resolve it. consequences is optional — see
    Phase 12E."""
    cq = _get_character_quest(db, character_id, quest_id)
    if cq.status != QuestStatus.ACTIVE:
        raise QuestLifecycleError(
            f"Não é possível falhar uma missão com status {cq.status}."
        )
    cq.status = QuestStatus.FAILED
    db.flush()
    log_event(
        db,
        campaign_id,
        EventType.QUEST_FAILED,
        actor_type="character",
        actor_id=character_id,
        payload={"quest_id": quest_id, "reason": reason},
    )
    apply_quest_consequences(db, campaign_id, character_id, consequences)
    return cq


def _transition_quest(
    db: Session,
    campaign_id: str,
    quest_id: str,
    *,
    new_status: QuestStatus,
    event_type: EventType,
    payload: dict,
) -> Quest:
    quest = db.get(Quest, quest_id)
    if quest is None:
        raise QuestLifecycleError(f"Missão desconhecida: {quest_id}")
    if quest.status != QuestStatus.AVAILABLE:
        raise QuestLifecycleError(
            f"'{quest.name}' já não está mais disponível ({quest.status})."
        )
    quest.status = new_status
    db.flush()
    log_event(db, campaign_id, event_type, actor_type="world", payload=payload)
    return quest


def cancel_quest(db: Session, campaign_id: str, quest_id: str, *, reason: str = "") -> Quest:
    """The requester withdraws the request, or circumstances make it moot —
    a world-level resolution independent of any one character's progress."""
    return _transition_quest(
        db,
        campaign_id,
        quest_id,
        new_status=QuestStatus.CANCELLED,
        event_type=EventType.QUEST_CANCELLED,
        payload={"quest_id": quest_id, "reason": reason},
    )


def expire_quest(db: Session, campaign_id: str, quest_id: str) -> Quest:
    """The opportunity's time window passed — see Phase 12D."""
    return _transition_quest(
        db,
        campaign_id,
        quest_id,
        new_status=QuestStatus.EXPIRED,
        event_type=EventType.QUEST_EXPIRED,
        payload={"quest_id": quest_id},
    )


def resolve_quest_externally(db: Session, campaign_id: str, quest_id: str, *, note: str = "") -> Quest:
    """Someone other than the protagonist resolved the underlying situation
    — see Phase 12H/12K. The world does not wait for Logan."""
    return _transition_quest(
        db,
        campaign_id,
        quest_id,
        new_status=QuestStatus.RESOLVED_EXTERNALLY,
        event_type=EventType.QUEST_RESOLVED_EXTERNALLY,
        payload={"quest_id": quest_id, "note": note},
    )


def complete_objective(db: Session, campaign_id: str, character_id: str, objective_id: str) -> CharacterQuestObjective:
    entry = (
        db.query(CharacterQuestObjective)
        .filter(
            CharacterQuestObjective.character_id == character_id,
            CharacterQuestObjective.objective_id == objective_id,
        )
        .first()
    )
    if not entry:
        entry = CharacterQuestObjective(character_id=character_id, objective_id=objective_id, completed=True)
        db.add(entry)
    else:
        entry.completed = True
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.QUEST_OBJECTIVE_COMPLETED,
        actor_type="character",
        actor_id=character_id,
        payload={"objective_id": objective_id},
    )

    objective = db.get(QuestObjective, objective_id)
    if objective:
        # Optional objectives (Phase 12C) never block quest completion —
        # only the required ones need to be in completed_ids below.
        remaining = (
            db.query(QuestObjective)
            .filter(
                QuestObjective.quest_id == objective.quest_id,
                QuestObjective.optional.is_(False),
            )
            .all()
        )
        completed_ids = {
            c.objective_id
            for c in db.query(CharacterQuestObjective).filter(
                CharacterQuestObjective.character_id == character_id, CharacterQuestObjective.completed.is_(True)
            )
        }
        if all(o.id in completed_ids for o in remaining):
            cq = (
                db.query(CharacterQuest)
                .filter(CharacterQuest.character_id == character_id, CharacterQuest.quest_id == objective.quest_id)
                .first()
            )
            if cq and cq.status != QuestStatus.COMPLETED:
                cq.status = QuestStatus.COMPLETED
                log_event(
                    db,
                    campaign_id,
                    EventType.QUEST_COMPLETED,
                    actor_type="character",
                    actor_id=character_id,
                    payload={"quest_id": objective.quest_id},
                )

    return entry


def list_character_quests(db: Session, character_id: str) -> list[CharacterQuest]:
    return db.query(CharacterQuest).filter(CharacterQuest.character_id == character_id).all()


def check_deadlines(db: Session, campaign_id: str, character_id: str | None = None) -> None:
    """Phase 12D: failure must be real — a quest does not stay frozen just
    because nobody is interacting with it. Call this whenever world time
    actually advances (see engine.py). Expires any AVAILABLE Quest whose
    opportunity window passed, and — if character_id is given — fails that
    character's ACTIVE participations whose own deadline passed. Most
    quests have no deadline at all and are untouched by this."""
    now = get_world_time(db, campaign_id).total_minutes()

    expiring = (
        db.query(Quest)
        .filter(
            Quest.status == QuestStatus.AVAILABLE,
            Quest.deadline_world_minute.isnot(None),
            Quest.deadline_world_minute <= now,
        )
        .all()
    )
    for quest in expiring:
        # The opportunity-window deadline is about nobody having claimed it
        # in time — once a character is actively on it, catching the
        # window is moot; their own CharacterQuest.deadline_world_minute
        # (if any) governs their participation from here instead.
        already_claimed = (
            db.query(CharacterQuest)
            .filter(CharacterQuest.quest_id == quest.id, CharacterQuest.status == QuestStatus.ACTIVE)
            .first()
            is not None
        )
        if already_claimed:
            continue
        expire_quest(db, campaign_id, quest.id)

    if character_id is None:
        return

    failing = (
        db.query(CharacterQuest)
        .filter(
            CharacterQuest.character_id == character_id,
            CharacterQuest.status == QuestStatus.ACTIVE,
            CharacterQuest.deadline_world_minute.isnot(None),
            CharacterQuest.deadline_world_minute <= now,
        )
        .all()
    )
    for cq in failing:
        fail_quest(db, campaign_id, character_id, cq.quest_id, reason="O prazo da missão expirou.")


def active_character_quests(db: Session, character_id: str) -> list[tuple[CharacterQuest, Quest]]:
    links = (
        db.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character_id, CharacterQuest.status == QuestStatus.ACTIVE)
        .all()
    )
    active = []
    for link in links:
        quest = db.get(Quest, link.quest_id)
        if quest is not None:
            active.append((link, quest))
    return active


def evaluate_objective_trigger(
    db: Session,
    campaign_id: str,
    character_id: str,
    trigger_type: ObjectiveTriggerType,
    *,
    subject_id: str | None = None,
) -> list[CharacterQuestObjective]:
    """The Objective Evaluator (Phase 12B). Call this after an authoritative
    backend fact occurs — an NPC was actually talked to, a location was
    actually reached, and so on (see the call sites in engine.py) — and any
    not-yet-completed objective on the character's active quests whose
    trigger matches is completed. The LLM never calls this and never
    decides the outcome; only real state changes reach here.

    A trigger with no trigger_subject_id matches any subject_id for that
    trigger_type; one with a trigger_subject_id requires an exact match.
    """
    completed: list[CharacterQuestObjective] = []
    for _cq, quest in active_character_quests(db, character_id):
        objectives = (
            db.query(QuestObjective)
            .filter(QuestObjective.quest_id == quest.id, QuestObjective.trigger_type == trigger_type)
            .all()
        )
        for objective in objectives:
            if (
                objective.trigger_subject_id is not None
                and objective.trigger_subject_id != subject_id
            ):
                continue
            already_done = (
                db.query(CharacterQuestObjective)
                .filter(
                    CharacterQuestObjective.character_id == character_id,
                    CharacterQuestObjective.objective_id == objective.id,
                    CharacterQuestObjective.completed.is_(True),
                )
                .first()
            )
            if already_done:
                continue
            completed.append(complete_objective(db, campaign_id, character_id, objective.id))
    return completed
