from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TerrainConfig(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    terrain_version: Literal[1] = 1
    sample_intervals: Literal[4, 8, 16, 32] = 16
    # Physical wavelengths stay useful for exploration even on enormous planets.
    regional_wavelength_m: int = Field(default=128_000, ge=8_192, le=512_000)
    relief_scale_ppm: int = Field(default=1_000_000, ge=0, le=2_000_000)
    base_samples_per_wavelength: int = Field(default=16, ge=8, le=64)
    max_patch_samples: int = Field(default=1089, ge=25, le=1089)
    max_patch_bytes: int = Field(default=131_072, ge=4096, le=262_144)
    max_patch_span_m: int = Field(default=1_000_000, ge=1, le=10_000_000)
    max_hydro_samples: int = Field(default=4096, ge=5, le=16384)

    @field_validator("terrain_version", "sample_intervals", mode="before")
    @classmethod
    def version_integer(cls, value):
        if type(value) is not int:
            raise ValueError("T1 needs an explicit integer version")
        return value
