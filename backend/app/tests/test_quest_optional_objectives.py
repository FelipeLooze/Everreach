"""Phase 12C — Optional Objectives.

An optional objective is still a real, trackable, completable objective —
it just never blocks the quest from finishing. Not every quest needs one.
"""

from app.core.enums import ObjectiveTriggerType, QuestStatus
from app.db.models.quest import CharacterQuest, Quest, QuestObjective
from app.game.character.service import create_character
from app.game.quests.service import complete_objective, start_quest
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Optional Objectives")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, character


def _quest_with_objectives(db_session, region_id):
    quest = Quest(region_id=region_id, name="Encontrar Mira", description="")
    db_session.add(quest)
    db_session.flush()
    required = QuestObjective(
        quest_id=quest.id, description="Encontrar Mira.", order=0, optional=False
    )
    optional = QuestObjective(
        quest_id=quest.id, description="Descobrir por que Mira partiu.", order=1, optional=True
    )
    db_session.add_all([required, optional])
    db_session.flush()
    return quest, required, optional


def test_quest_completes_once_required_objective_is_done_even_if_optional_is_not(db_session):
    campaign, region, character = _setup(db_session)
    quest, required, optional = _quest_with_objectives(db_session, region.id)
    start_quest(db_session, character.id, quest.id)

    complete_objective(db_session, campaign.id, character.id, required.id)

    cq = (
        db_session.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character.id, CharacterQuest.quest_id == quest.id)
        .first()
    )
    assert cq.status == QuestStatus.COMPLETED


def test_completing_only_the_optional_objective_does_not_complete_the_quest(db_session):
    campaign, region, character = _setup(db_session)
    quest, required, optional = _quest_with_objectives(db_session, region.id)
    start_quest(db_session, character.id, quest.id)

    complete_objective(db_session, campaign.id, character.id, optional.id)

    cq = (
        db_session.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character.id, CharacterQuest.quest_id == quest.id)
        .first()
    )
    assert cq.status == QuestStatus.ACTIVE


def test_optional_objective_is_still_trackable_as_completed(db_session):
    campaign, region, character = _setup(db_session)
    quest, required, optional = _quest_with_objectives(db_session, region.id)
    start_quest(db_session, character.id, quest.id)

    entry = complete_objective(db_session, campaign.id, character.id, optional.id)

    assert entry.completed is True


def test_objectives_default_to_required(db_session):
    campaign, region, character = _setup(db_session)
    quest = Quest(region_id=region.id, name="Missão simples", description="")
    db_session.add(quest)
    db_session.flush()
    objective = QuestObjective(quest_id=quest.id, description="Fazer algo.", order=0)
    db_session.add(objective)
    db_session.flush()

    assert objective.optional is False
