"""T1 continuous height authority. Full spectrum is independent of query LOD."""
from collections import OrderedDict
from dataclasses import dataclass
from math import isqrt
from threading import RLock
import hashlib
import json

from ..formation_config import calibrated_scale
from ..formation_tectonics import evaluate
from ..randomness import coordinate_seed
from ..sphere_topology import SurfacePoint
from .address import chart, point_on_face
from .config import TerrainConfig

PRECISION = 2**64
NOISE_SCALE = 10_000_000_000
AMPLITUDES_MM = (120_000, 55_000, 25_000, 12_000, 5_000, 2_000, 800, 300)


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class TerrainPlan:
    source: object
    config: TerrainConfig
    source_checksum: str
    signature: str
    base_level: int

    def to_dict(self):
        return {"kind": "local_terrain_t1", "terrain_version": 1, "source_signature": self.source.signature,
                "source_checksum": self.source_checksum, "signature": self.signature,
                "config": self.config.model_dump(), "base_level": self.base_level,
                "height_unit": "mm", "authority": "full_spectrum_point_field",
                "minimum_wavelength_m": max(1, self.config.regional_wavelength_m//4**7)}


def build_terrain_plan(source, config=None):
    config = config or TerrainConfig()
    if source.config.generator_version != 4:
        raise ValueError("T1 is explicit V4 opt-in; legacy terrain is not converted")
    wavelength = calibrated_scale(source.config)["detail_wavelength_m"]
    level = 0
    while level < 24 and 2*source.config.radius_m*config.base_samples_per_wavelength > wavelength*2**level:
        level += 1
    source_hash = checksum(source.to_dict())
    sig = checksum(["local-terrain-t1", source.signature, source_hash, config.model_dump(), level])[:24]
    return TerrainPlan(source, config, source_hash, sig, level)


def _direction(point):
    norm = isqrt(sum(v*v for v in point.xyz)*PRECISION**2)
    return tuple(v*PRECISION**2//norm for v in point.xyz)


def _noise(seed, direction, radius, wavelength, octave):
    axes = [divmod(v*radius//wavelength, PRECISION) for v in direction]
    def node(x, y, z):
        return (coordinate_seed(seed, 1, "terrain_t1", octave, axes[0][0]+x,
                                axes[1][0]+y, axes[2][0]+z)%20001-10000)*1_000_000
    def blend(a, b, t):
        return a+(b-a)*t*t*(3*PRECISION-2*t)//PRECISION**3
    rows = [[blend(node(0, y, z), node(1, y, z), axes[0][1]) for y in range(2)] for z in range(2)]
    return blend(*(blend(*row, axes[1][1]) for row in rows), axes[2][1])


class TerrainSampler:
    """At most 2048 V4 corners; no global/local tile grids retained in cache."""
    def __init__(self, plan):
        self.plan = plan
        self._corners = OrderedDict()
        self._lock = RLock()

    def _corner(self, point):
        with self._lock:
            if point in self._corners:
                self._corners.move_to_end(point)
                return self._corners[point]
        source = self.plan.source
        value = evaluate(source.seed, source.config, source.plates, point, causes=False)
        result = value["elevation_m"]*1000, value["terms_m"]["tectonic"]*1000
        with self._lock:
            self._corners[point] = result
            while len(self._corners) > 2048:
                self._corners.popitem(last=False)
        return result

    def base(self, point):
        face, u, v, d = chart(point)
        n = 2**self.plan.base_level
        x, y = min(n-1, u*n//d), min(n-1, v*n//d)
        tx, ty = u*n-x*d, v*n-y*d
        corners = [self._corner(point_on_face(face, x+dx, y+dy, n))
                   for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1))]
        def interpolate(index):
            a, b, c, e = [p[index] for p in corners]
            return (a*(d-tx)*(d-ty)+b*tx*(d-ty)+c*(d-tx)*ty+e*tx*ty)//d**2
        # Conservative slope proxy per chart coordinate; controls roughness, not movement.
        span_mm = max(1, self.plan.source.config.radius_m*1000//n)
        slope_ppm = min(1_000_000, max(abs(corners[1][0]-corners[0][0]),
            abs(corners[2][0]-corners[0][0]), abs(corners[3][0]-corners[1][0]),
            abs(corners[3][0]-corners[2][0]))*1_000_000//span_mm)
        # Do not use cell-local slope for amplitude: it can jump at cell boundaries.
        return interpolate(0), interpolate(1), slope_ppm

    def sample(self, point):
        if not isinstance(point, SurfacePoint):
            raise ValueError("T1 requires an exact SurfacePoint")
        base, tectonic, slope = self.base(point)
        source, config = self.plan.source, self.plan.config
        direction = _direction(point)
        rugged_ppm = 250_000+min(750_000, abs(tectonic)*750_000//3_000_000)
        offsets = []
        for octave, amplitude in enumerate(AMPLITUDES_MM):
            wavelength = max(1, config.regional_wavelength_m//4**octave)
            value = _noise(source.seed, direction, source.config.radius_m, wavelength, octave)
            # Alternating broad valleys / narrower ridge shoulders; static morphology,
            # never a declaration of erosion, drainage direction or flowing water.
            shaped = value if octave%2 else value*abs(value)//NOISE_SCALE
            offsets.append(shaped*amplitude*rugged_ppm*config.relief_scale_ppm)
        # Preserve reconstructed coastline sign continuously; no new land classification
        # is allowed to overwrite old R1 identities. Reconstruction mismatch is explicit.
        coast_distance = abs(base-source.config.sea_level_m*1000)
        envelope = min(1_000_000, coast_distance*1_000_000//500_000)
        delta = sum(offsets)*envelope//(NOISE_SCALE*10**18)
        return {"terrain_version": 1, "signature": self.plan.signature, "point": list(point.xyz),
                "height_mm": base+delta, "base_v4_reconstructed_mm": base, "detail_mm": delta,
                "regional_detail_mm": sum(offsets[:3])*envelope//(NOISE_SCALE*10**18),
                "tectonic_context_mm": tectonic, "slope_proxy_ppm": slope,
                "authority": "full_spectrum_point_field", "base_level": self.plan.base_level,
                "minimum_wavelength_m": max(1, config.regional_wavelength_m//4**7),
                "substrate_contract": "tectonic_context_and_morphology_not_material_assignment"}

    def cache_size(self):
        with self._lock:
            return len(self._corners)
