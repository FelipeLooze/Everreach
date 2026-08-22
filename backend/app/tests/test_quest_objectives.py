"""Phase 12B — Objectives.

Objective completion previously came from a free-text substring match
("is the NPC's name inside the objective's description?") tied to the TALK
intent only. That's exactly the "kill X / collect Y / go to Z" flattening
the Phase 12 spec calls out — and it wasn't even backend-authoritative
against a specific NPC, just a name string. The Objective Evaluator
(evaluate_objective_trigger) replaces it: an objective declares a
structured trigger_type + optional trigger_subject_id, and it is only
completed when that exact authoritative fact occurs (an NPC was actually
talked to, a location was actually reached) — never from narration text.
"""

from app.core.enums import ObjectiveTriggerType, ObjectiveType
from app.db.models.location import Location, LocationConnection
from app.db.models.npc import NPC
from app.db.models.quest import CharacterQuestObjective, Quest, QuestObjective
from app.game.character.service import create_character
from app.game.discovery.service import discover_connection, set_location_discovery
from app.game.quests.service import evaluate_objective_trigger, start_quest
from app.game.world.seed import create_campaign, seed_initial_region
from app.core.enums import DiscoveryStatus
from app.game import engine
from app.ai.intent_parser import Intent
from app.core.enums import ActionIntentType


def _setup(db_session):
    campaign = create_campaign(db_session, "Quest Objectives")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def _quest_with_objective(db_session, region_id, *, trigger_type, subject_id=None):
    quest = Quest(region_id=region_id, name="Missão de Teste", description="")
    db_session.add(quest)
    db_session.flush()
    objective = QuestObjective(
        quest_id=quest.id,
        description="Objetivo de teste.",
        objective_type=ObjectiveType.INVESTIGATION,
        trigger_type=trigger_type,
        trigger_subject_id=subject_id,
    )
    db_session.add(objective)
    db_session.flush()
    return quest, objective


def test_evaluate_objective_trigger_completes_a_matching_manualless_objective(db_session):
    campaign, region, village, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    quest, objective = _quest_with_objective(
        db_session, region.id, trigger_type=ObjectiveTriggerType.TALK_TO_NPC, subject_id=osgar.id
    )
    start_quest(db_session, character.id, quest.id)

    completed = evaluate_objective_trigger(
        db_session, campaign.id, character.id, ObjectiveTriggerType.TALK_TO_NPC, subject_id=osgar.id
    )

    assert len(completed) == 1
    row = (
        db_session.query(CharacterQuestObjective)
        .filter(CharacterQuestObjective.objective_id == objective.id)
        .first()
    )
    assert row.completed is True


def test_evaluate_objective_trigger_ignores_a_different_subject(db_session):
    campaign, region, village, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    mira = db_session.query(NPC).filter(NPC.role == "ferreira").first()
    quest, objective = _quest_with_objective(
        db_session, region.id, trigger_type=ObjectiveTriggerType.TALK_TO_NPC, subject_id=osgar.id
    )
    start_quest(db_session, character.id, quest.id)

    completed = evaluate_objective_trigger(
        db_session, campaign.id, character.id, ObjectiveTriggerType.TALK_TO_NPC, subject_id=mira.id
    )

    assert completed == []


def test_evaluate_objective_trigger_ignores_a_different_trigger_type(db_session):
    campaign, region, village, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    quest, objective = _quest_with_objective(
        db_session, region.id, trigger_type=ObjectiveTriggerType.TALK_TO_NPC, subject_id=osgar.id
    )
    start_quest(db_session, character.id, quest.id)

    completed = evaluate_objective_trigger(
        db_session, campaign.id, character.id, ObjectiveTriggerType.REACH_LOCATION, subject_id=osgar.id
    )

    assert completed == []


def test_manual_trigger_objectives_are_never_auto_completed(db_session):
    campaign, region, village, character = _setup(db_session)
    quest, objective = _quest_with_objective(
        db_session, region.id, trigger_type=ObjectiveTriggerType.MANUAL
    )
    start_quest(db_session, character.id, quest.id)

    completed = evaluate_objective_trigger(
        db_session, campaign.id, character.id, ObjectiveTriggerType.TALK_TO_NPC, subject_id="anything"
    )

    assert completed == []


def test_evaluate_objective_trigger_is_idempotent(db_session):
    campaign, region, village, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    quest, objective = _quest_with_objective(
        db_session, region.id, trigger_type=ObjectiveTriggerType.TALK_TO_NPC, subject_id=osgar.id
    )
    start_quest(db_session, character.id, quest.id)

    evaluate_objective_trigger(
        db_session, campaign.id, character.id, ObjectiveTriggerType.TALK_TO_NPC, subject_id=osgar.id
    )
    second = evaluate_objective_trigger(
        db_session, campaign.id, character.id, ObjectiveTriggerType.TALK_TO_NPC, subject_id=osgar.id
    )

    assert second == []


def test_reaching_a_location_completes_a_matching_objective_via_move(db_session):
    campaign, region, village, character = _setup(db_session)
    forest = db_session.query(Location).filter(Location.region_id == region.id, Location.type == "forest").first()
    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )
    connection.danger = 0
    discover_connection(db_session, character.id, connection.id)
    set_location_discovery(db_session, character.id, forest.id, DiscoveryStatus.DISCOVERED)

    quest, objective = _quest_with_objective(
        db_session, region.id, trigger_type=ObjectiveTriggerType.REACH_LOCATION, subject_id=forest.id
    )
    start_quest(db_session, character.id, quest.id)

    intent = Intent(type=ActionIntentType.MOVE, target=forest.name, raw_text="Vou ao bosque")
    engine._apply_intent(db_session, campaign.id, character, intent, None)

    row = (
        db_session.query(CharacterQuestObjective)
        .filter(CharacterQuestObjective.objective_id == objective.id)
        .first()
    )
    assert row is not None and row.completed is True
