from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HydrologyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    hydrology_version: Literal[1] = 1
    source_generator_version: Literal[4] = 4
    level: int = Field(default=5, ge=2, le=5)
    channel_min_area_ppm: int = Field(default=125, ge=1, le=1_000_000)
    major_channel_area_ppm: int = Field(default=500, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def validate_lod(self):
        if self.major_channel_area_ppm < self.channel_min_area_ppm:
            raise ValueError("Major-channel threshold must not be below channel threshold")
        return self
