from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegionalConfig(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    regional_version: Literal[1] = 1
    formation_spacing_m: int = Field(default=8000, ge=2000, le=32000)

    @field_validator("regional_version", mode="before")
    @classmethod
    def exact(cls,v):
        if type(v) is not int:
            raise ValueError("JR1 version must be an integer")
        return v


class RegionalPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    policy_version: Literal[1] = 1
    rate_factor_ppm: int = Field(default=1000000, ge=0, le=2000000)

    @field_validator("policy_version", mode="before")
    @classmethod
    def exact(cls,v):
        if type(v) is not int:
            raise ValueError("JR1 policy version must be an integer")
        return v
