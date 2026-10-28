from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import WorldConfig


class SphereConfig(BaseModel):
    """V2 radial cube-sphere; cell sizes vary, radius is physical metres."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    config_version: Literal[2] = 2
    generator_version: Literal[2] = 2
    topology: Literal["cube_sphere"] = "cube_sphere"
    radius_m: int = Field(default=6_371_000, ge=1_000, le=1_000_000_000_000)
    sector_level: int = Field(default=10, ge=0, le=24)
    macro_level: int = Field(default=4, ge=0, le=12)
    sample_intervals: Literal[1, 2, 4, 8, 16, 32] = 4
    sea_level_m: int = Field(default=0, ge=-10_000, le=10_000)

    @field_validator("sample_intervals", mode="before")
    @classmethod
    def reject_boolean_literals(cls, value):
        if type(value) is not int:
            raise ValueError("Sample intervals must be an integer")
        return value


def parse_config(data: dict) -> WorldConfig | SphereConfig:
    version = data.get("config_version")
    if type(version) is not int:
        raise ValueError("An explicit integer configuration version is required")
    if version == 1:
        return WorldConfig.model_validate(data)
    if version == 2:
        return SphereConfig.model_validate(data)
    if version == 3:
        from .formation_config import FormationConfig
        return FormationConfig.model_validate(data)
    if version == 4:
        from .formation_v4 import FormationConfigV4
        return FormationConfigV4.model_validate(data)
    raise ValueError(f"Unsupported world configuration version: {version}")
