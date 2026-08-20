from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.schemas.game_state import GameStateResponse


class ActionRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    action_key: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=180,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9:_-]*$",
        ),
    ] | None = None
    technique_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ] | None = None


class ActionResponse(BaseModel):
    narrative: str
    narrator_unavailable: bool
    mechanical_summary: str
    intent_type: str
    warnings: list[str]
    state: GameStateResponse
