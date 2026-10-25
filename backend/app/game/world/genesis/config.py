from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorldConfig(BaseModel):
    """V1 finite cylindrical atlas. Distances are atlas metres, not geodesics."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    config_version: Literal[1] = 1
    generator_version: Literal[1] = 1
    topology: Literal["cylinder"] = "cylinder"
    width_m: int = Field(default=40_960_000, gt=0, le=1_000_000_000)
    height_m: int = Field(default=20_480_000, gt=0, le=1_000_000_000)
    macro_cell_m: int = Field(default=512_000, gt=0)
    sector_m: int = Field(default=16_000, gt=0)
    sample_step_m: int = Field(default=4_000, gt=0)
    sea_level_m: int = Field(default=0, ge=-10_000, le=10_000)

    @model_validator(mode="after")
    def validate_grid(self):
        if any(size % self.macro_cell_m or size % self.sector_m
               for size in (self.width_m, self.height_m)):
            raise ValueError("Atlas dimensions must be multiples of macro and sector sizes")
        if self.sector_m % self.sample_step_m or self.sector_m // self.sample_step_m > 64:
            raise ValueError("Sector must contain 1..64 whole sample intervals")
        if self.width_m // self.macro_cell_m < 4 or self.height_m // self.macro_cell_m < 2:
            raise ValueError("Atlas needs at least 4 by 2 macro cells")
        return self
