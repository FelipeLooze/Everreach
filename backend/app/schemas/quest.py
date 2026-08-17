from pydantic import BaseModel


class QuestObjectiveResponse(BaseModel):
    id: str
    description: str
    completed: bool


class QuestResponse(BaseModel):
    quest_id: str
    name: str
    description: str
    status: str
    objectives: list[QuestObjectiveResponse]


class QuestListResponse(BaseModel):
    quests: list[QuestResponse]
