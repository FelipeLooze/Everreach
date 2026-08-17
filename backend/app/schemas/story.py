from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class StoryEntryResponse(BaseModel):
    id: str
    kind: Literal["player", "narrator"]
    text: str
    created_at: datetime


class StoryLogResponse(BaseModel):
    entries: list[StoryEntryResponse]
