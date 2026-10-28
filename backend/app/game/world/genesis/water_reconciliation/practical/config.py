from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PracticalConfig(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    practical_version: Literal[1] = 1
    allocation_version: Literal[1] = 1
    capacity_version: Literal[1] = 1
    grid_intervals: Literal[8, 16] = 16
    target_spacing_m: int = Field(default=4, ge=1, le=8)
    cross_step_mm: int = Field(default=500, ge=100, le=1000)
    cross_half_intervals: int = Field(default=8, ge=4, le=16)
    manning_n_milli: int = Field(default=75, ge=30, le=150)
    velocity_limit_mm_s: int = Field(default=10, ge=1, le=1000)
    capacity_factor_ppm: int = Field(default=100_000, ge=1, le=1_000_000)
    episode_minutes: int = Field(default=1440, ge=1, le=1440)
    max_samples: int = Field(default=32768, ge=1024, le=65536)
    max_candidate_edges: int = Field(default=128, ge=1, le=256)
    max_macro_candidates: int = Field(default=8, ge=1, le=16)
    max_tiles_per_macro: int = Field(default=4, ge=1, le=8)

    @field_validator("practical_version", "allocation_version", "capacity_version", "grid_intervals", mode="before")
    @classmethod
    def exact_versions(cls, v):
        if type(v) is not int:
            raise ValueError("P1 versions and intervals must be integer values")
        return v
