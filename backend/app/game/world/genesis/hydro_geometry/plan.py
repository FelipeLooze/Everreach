from dataclasses import dataclass
from ..terrain.field import checksum
from .config import G1Config


@dataclass(frozen=True)
class GeometryPlan:
    terrain: object
    hydrology: object
    hr_signature: str
    config: G1Config
    signature: str
    hydrology_checksum: str

    def to_dict(self):
        return {"kind": "local_hydro_geometry_g1", "geometry_version": 1, "signature": self.signature,
            "terrain_signature": self.terrain.signature, "terrain_checksum": checksum(self.terrain.to_dict()),
            "hydrology_signature": self.hydrology.signature, "hydrology_checksum": self.hydrology_checksum,
            "hr_signature": self.hr_signature, "config": self.config.model_dump(),
            "coast_policy_version": 1, "height_authority": "T1", "water_occupation": "not_modeled"}


def build_geometry_plan(terrain, hydrology, hr_signature, config=None):
    config = config or G1Config()
    if (terrain.source.signature != hydrology.source_signature or
            terrain.source.config.radius_m != hydrology.radius_m or not isinstance(hr_signature, str) or not hr_signature):
        raise ValueError("G1 requires matching pinned T1/H1/HR1 sources")
    source_hash = checksum(hydrology.to_dict())
    sig = signature_for(terrain, source_hash, hr_signature, config)
    return GeometryPlan(terrain, hydrology, hr_signature, config, sig, source_hash)


def signature_for(terrain, h1_checksum, hr_signature, config):
    return checksum(["hydro-geometry-g1", terrain.to_dict(), h1_checksum, hr_signature, config.model_dump()])[:24]
