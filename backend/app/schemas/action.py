from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.schemas.game_state import GameStateResponse


class ActionRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ActionResponse(BaseModel):
    narrative: str
    narrator_unavailable: bool
    mechanical_summary: str
    intent_type: str
    warnings: list[str]
    state: GameStateResponse
