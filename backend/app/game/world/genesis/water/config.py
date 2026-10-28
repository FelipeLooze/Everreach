from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WaterConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    water_version: Literal[1] = 1
    source_climate_version: Literal[1, 2] = 2
    warmup_years: int = Field(default=2, ge=0, le=7)
    soil_capacity_mm: int = Field(default=150, ge=0, le=2000)
    surface_capacity_mm: int = Field(default=10, ge=0, le=1000)
    infiltration_mm_per_day: int = Field(default=8, ge=0, le=1000)
    soil_release_ppm_per_day: int = Field(default=3000, ge=0, le=1_000_000)
    frozen_soil_factor_ppm: int = Field(default=100_000, ge=0, le=1_000_000)
    snow_melt_milli_mm_per_degree_day: int = Field(default=3000, ge=0, le=30_000)
    reservoir_wetted_area_ppm: int = Field(default=100_000, ge=0, le=1_000_000)
    channel_velocity_mm_s: int = Field(default=1000, ge=1, le=20_000)
    flow_presence_liters_per_second: int = Field(default=10, ge=0, le=1_000_000)

    @field_validator("water_version", "source_climate_version", mode="before")
    @classmethod
    def integer_versions(cls, value):
        if type(value) is not int:
            raise ValueError("Water and climate versions must be explicit integers")
        return value


C3_FORCING_CONTRACT='C3_R1_55_gross_precipitation_total_PET_v1'


class WaterConfigC3R155(WaterConfig):
    """W1 forcing extension; legacy WaterConfig dumps and defaults stay intact."""
    source_climate_version: Literal[3]=3
    forcing_contract: Literal['C3_R1_55_gross_precipitation_total_PET_v1']=C3_FORCING_CONTRACT


def parse_water_config(data):
    if data.get('forcing_contract')==C3_FORCING_CONTRACT:
        return WaterConfigC3R155.model_validate(data)
    return WaterConfig.model_validate(data)


def check_climate_contract(config,climate_config):
    if config.source_climate_version!=climate_config.climate_version:
        raise ValueError('W1 source climate version differs from explicit forcing contract')
    if climate_config.climate_version==3:
        from ..climate.v3 import ClimateConfigV3R1
        if (not isinstance(config,WaterConfigC3R155) or not isinstance(climate_config,ClimateConfigV3R1)
                or climate_config.land_recycling_ppm!=550000):
            raise ValueError('W1 C3 forcing requires explicit R1-55 contract; no legacy C3 relabelling')
