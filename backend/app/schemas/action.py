from typing import Annotated,Literal

from pydantic import BaseModel, StringConstraints,ConfigDict,Field,model_validator

from app.schemas.game_state import GameStateResponse


class PlantActionRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    kind: Literal["look","observe","harvest","remove"]
    individual_id: str|None=Field(default=None,max_length=100)
    part_id: str|None=Field(default=None,max_length=100)
    quantity: int=Field(default=1,ge=1,le=10000)
    tool_instance_id: str|None=Field(default=None,max_length=100)

    @model_validator(mode="after")
    def target(self):
        if self.kind!="look" and not self.individual_id:raise ValueError("A materialized individual is required")
        if self.kind=="harvest" and (not self.part_id or not self.tool_instance_id):raise ValueError("Part and actual tool required")
        if self.kind=="remove" and not self.tool_instance_id:raise ValueError("Actual tool required")
        return self


class FormationActionRequest(BaseModel):
    model_config=ConfigDict(extra="forbid", strict=True)
    kind: Literal["inspect","interact"]


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
    plant_action: PlantActionRequest|None=None
    formation_action: FormationActionRequest|None=None

    @model_validator(mode="after")
    def one_action(self):
        if sum(x is not None for x in (self.plant_action,self.formation_action,self.technique_id)) > 1:raise ValueError("Choose one structured action")
        return self


class ActionResponse(BaseModel):
    narrative: str
    narrator_unavailable: bool
    mechanical_summary: str
    intent_type: str
    warnings: list[str]
    state: GameStateResponse
    plant_result: dict|None=None
    formation_result: dict|None=None


class ActionUndoStatusResponse(BaseModel):
    available: bool
    action_text: str | None = None
    mechanical_summary: str | None = None


class ActionUndoRequest(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ActionUndoResponse(BaseModel):
    state: GameStateResponse
