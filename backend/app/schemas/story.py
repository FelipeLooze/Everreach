from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints


class StoryEntryResponse(BaseModel):
    id: str
    kind: Literal["player", "narrator"]
    text: str
    created_at: datetime


class StoryLogResponse(BaseModel):
    entries: list[StoryEntryResponse]


class StoryRegenerationRequest(BaseModel):
    feedback: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class StoryRegenerationResponse(BaseModel):
    entry: StoryEntryResponse
