from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from ..sphere_topology import SurfacePoint
from ..terrain.address import TerrainTile, chart


class G1Config(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    geometry_version: Literal[1] = 1
    max_samples: int = Field(default=16384, ge=16, le=32768)
    max_expansions: int = Field(default=4096, ge=1, le=4096)
    max_payload_bytes: int = Field(default=2_097_152, ge=4096, le=8_388_608)
    max_sections: int = Field(default=8, ge=0, le=16)
    section_step_m: int = Field(default=25, ge=1, le=1000)
    section_half_intervals: int = Field(default=4, ge=2, le=8)

    @field_validator("geometry_version", mode="before")
    @classmethod
    def integer_version(cls, v):
        if type(v) is not int:
            raise ValueError("G1 requires an integer version")
        return v


class Anchor(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    id: str = Field(min_length=1, max_length=240)
    point: list[int] = Field(min_length=3, max_length=3)
    role: Literal["ingress", "outlet", "relay"]
    reference_head_mm: int | None = None

    @field_validator("point")
    @classmethod
    def exact_canonical(cls, v):
        if list(SurfacePoint(*v).xyz) != v:
            raise ValueError("G1 anchors need canonical rays")
        return v


class GeometryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    tile: list[int] = Field(min_length=4, max_length=4)
    anchors: list[Anchor] = Field(min_length=1, max_length=12)
    grid_intervals: Literal[4, 8, 16, 32] = 8
    target_spacing_m: int = Field(default=100, ge=1, le=1_000_000)
    sample_budget: int = Field(default=8192, ge=16, le=32768)
    expansion_budget: int = Field(default=4096, ge=1, le=4096)
    origin: Literal["explicit_boundary_contract", "hr1_legacy", "hr1_t1_candidates"] = "explicit_boundary_contract"
    provenance: dict = Field(default_factory=dict)

    @field_validator("grid_intervals", mode="before")
    @classmethod
    def integer_intervals(cls, v):
        if type(v) is not int:
            raise ValueError("G1 needs integer intervals")
        return v

    @model_validator(mode="after")
    def validate_geometry(self):
        tile = TerrainTile(*self.tile)
        if len({a.id for a in self.anchors}) != len(self.anchors) or sum(a.role == "outlet" for a in self.anchors) != 1:
            raise ValueError("G1 requires unique anchor IDs and exactly one prescribed outlet")
        for a in self.anchors:
            _, u, v, d = chart(SurfacePoint(*a.point), tile.face)
            n = 2**tile.level
            if d <= 0 or not tile.x*d <= u*n <= (tile.x+1)*d or not tile.y*d <= v*n <= (tile.y+1)*d:
                raise ValueError("G1 anchor is outside the closed tile")
        return self

    def canonical(self):
        data = self.model_dump()
        data["anchors"].sort(key=lambda a: a["id"])
        return data
