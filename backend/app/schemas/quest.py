from pydantic import BaseModel


class QuestObjectiveResponse(BaseModel):
    """Phase 12G — Quests Without Magical Markers: this is the entire
    player-facing surface of an objective. Deliberately excludes
    trigger_type/trigger_subject_id (the Objective Evaluator's internal
    matching data, Phase 12B) and objective_type — there is no waypoint,
    exact target id, or coordinate here, only the same free-text
    description a person would have. See test_quest_no_magic_markers.py."""

    id: str
    description: str
    completed: bool


class QuestResponse(BaseModel):
    """See QuestObjectiveResponse — likewise excludes source,
    deadline_world_minute and any other backend-only Quest field."""

    quest_id: str
    name: str
    description: str
    status: str
    objectives: list[QuestObjectiveResponse]


class QuestListResponse(BaseModel):
    quests: list[QuestResponse]
