from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator


class EnvironmentConfig(BaseModel):
    model_config=ConfigDict(frozen=True,strict=True,extra="forbid")
    environment_version: Literal[1]=1
    reference_profile: Literal["EV-ECO-1.1.1_C2_P_over_PET"]="EV-ECO-1.1.1_C2_P_over_PET"
    range_overrides: dict[str,dict[str,list[int|float]]]=Field(default_factory=dict)
    cold_regime_max_mean_centi_c: int=1000
    forest_warmest_quarter_min_centi_c: int=500
    mountain_min_altitude_m: int=250
    mountain_min_tectonic_context_mm: int=800000
    ecotone_relative_score_ppm: int=Field(default=600000,ge=0,le=1000000)
    max_secondary: int=Field(default=4,ge=1,le=8)

    @field_validator("environment_version",mode="before")
    @classmethod
    def exact(cls,v):
        if type(v) is not int:
            raise ValueError("E1 version must be an integer")
        return v


class EnvironmentConfigC3(EnvironmentConfig):
    """Explicit C3 source profile; legacy E1 serialization is unchanged."""
    reference_profile: Literal["EV-ECO-1.1.1_C3_P_over_PET"]="EV-ECO-1.1.1_C3_P_over_PET"


def parse_environment_config(data):
    if data.get('reference_profile')=='EV-ECO-1.1.1_C3_P_over_PET':
        return EnvironmentConfigC3.model_validate(data)
    return EnvironmentConfig.model_validate(data)


def source_climate_version(config):
    return 3 if isinstance(config,EnvironmentConfigC3) else 2
