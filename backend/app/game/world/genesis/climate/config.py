from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ClimateConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    climate_version: Literal[1] = 1
    level: int = Field(default=5, ge=3, le=5)
    axial_tilt_mdeg: int = Field(default=23_440, ge=0, le=60_000)
    year_days: int = Field(default=360, ge=4, le=10_000)
    radiative_offset_centi_c: int = Field(default=-5200, ge=-15_000, le=5000)
    insolation_gain_centi_c: int = Field(default=26_000, ge=0, le=50_000)
    poleward_heat_transport_ppm: int = Field(default=150_000, ge=0, le=1_000_000)
    lapse_centi_c_per_km: int = Field(default=600, ge=0, le=1500)
    land_seasonal_response_ppm: int = Field(default=350_000, ge=0, le=1_000_000)
    ocean_seasonal_response_ppm: int = Field(default=100_000, ge=0, le=1_000_000)
    maritime_length_m: int | None = Field(default=None, ge=1, le=10**12)
    moisture_length_m: int | None = Field(default=None, ge=1, le=10**12)
    hadley_edge_mdeg: int = Field(default=30_000, ge=10_000, le=50_000)
    polar_edge_mdeg: int = Field(default=60_000, ge=50_000, le=85_000)
    wind_scale_milli_m_s: int = Field(default=8000, ge=0, le=100_000)
    itcz_shift_ppm: int = Field(default=250_000, ge=0, le=500_000)
    transport_iterations: int = Field(default=40, ge=8, le=64)
    base_condensation_ppm: int = Field(default=50_000, ge=0, le=500_000)
    convective_condensation_ppm: int = Field(default=300_000, ge=0, le=700_000)
    orographic_condensation_ppm_per_km: int = Field(default=150_000, ge=0, le=500_000)
    rain_scale_milli_mm_per_day: int = Field(default=12_000, ge=0, le=100_000)
    pet_scale_milli_mm_per_day: int = Field(default=4500, ge=0, le=30_000)

    @field_validator("climate_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("C1 requires an explicit integer version")
        return value

    @model_validator(mode="after")
    def validate_bands(self):
        if self.polar_edge_mdeg <= self.hadley_edge_mdeg:
            raise ValueError("Polar edge must be poleward of the Hadley edge")
        return self
