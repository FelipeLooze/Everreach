from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class GeologyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    geology_version: Literal[1] = 1
    expected_provinces: int = Field(default=192, ge=32, le=192)

    @field_validator("geology_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("J1 version must be an integer")
        return value
