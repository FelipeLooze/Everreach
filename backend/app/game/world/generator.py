"""Phase 15B — Initial Massive Region Generation: the generation pipeline.

This module is the orchestration home for turning a generation_seed into
persisted world structure. It starts small (15B: only region-level macro
identity) and grows one stage per Phase 15 subphase (15D subregions, 15E
geography, 15F settlements, ...), always called from
app.game.world.seed.seed_initial_region rather than replacing its public
entry point — 200+ existing tests already call
create_campaign()/seed_initial_region() as two separate steps, and Phase
15 does not need to break that shape to satisfy "the world must already
exist before the protagonist discovers it": seed_initial_region already
runs, in full, before app.api.routes.campaigns.start_world returns the
opening narrative — i.e. strictly before any voluntary player action.

Every stage function takes a random.Random already seeded for that stage
specifically (via derive_seed with a stage-specific salt) so adding a new
stage later never shifts the RNG stream consumed by unrelated stages.
"""

import random

from app.core.enums import DangerLevel, PopulationDensity, SubregionBiome
from app.game.world.content_pools import (
    ANCHOR_SUBREGION_NAME,
    CITY_DISTRICTS,
    CLIMATE_SUMMARIES,
    CULTURAL_SUMMARIES,
    GEOGRAPHY_BY_BIOME,
    HISTORICAL_SUMMARIES,
    POPULATION_TIER_BY_TYPE,
    SERVICES_BY_SETTLEMENT_TYPE,
    SETTLEMENT_NAME_PARTS_A,
    SETTLEMENT_NAME_PARTS_B,
    SETTLEMENT_PROFILE_BY_TYPE,
    SETTLEMENT_SERVICE_POOL,
    SETTLEMENT_TYPE_BY_BIOME,
    SUBREGION_CULTURE_SUMMARIES,
    SUBREGION_ECONOMY_SUMMARIES,
    SUBREGION_NAME_POOL,
)

CITY_SCALE_TYPES = ("MAJOR_CITY", "CITY")

MINOR_SETTLEMENTS_PER_SUBREGION = (1, 3)

MIN_SUBREGIONS = 8
MAX_SUBREGIONS = 1 + len(SUBREGION_NAME_POOL)  # anchor + every pool entry


def generate_region_identity(rng: random.Random) -> tuple[str, str, str]:
    """Picks (climate_summary, cultural_summary, historical_summary) for a
    Region from the curated pools, deterministically for a given rng."""
    return (
        rng.choice(CLIMATE_SUMMARIES),
        rng.choice(CULTURAL_SUMMARIES),
        rng.choice(HISTORICAL_SUMMARIES),
    )


class SubregionIdentity(dict):
    """Lightweight structured result of generate_subregion_identity —
    a dict subclass so callers can do both identity["biome"] and, if it
    reads better at a call site, identity.get(...) without a new import."""


def generate_subregion_identity(rng: random.Random, *, is_anchor: bool = False) -> SubregionIdentity:
    """Rolls (biome, danger_level, population_density, culture_summary,
    economy_summary) for one subregion. The anchor subregion (containing
    the fixed starting village) is constrained to stay playable at game
    start — plains, no worse than LOW danger — per the spec's own "do not
    place unavoidable lethal threats directly on the starting character"
    guidance; every other subregion rolls freely."""
    if is_anchor:
        biome = SubregionBiome.PLAINS
        danger_level = rng.choice([DangerLevel.SAFE, DangerLevel.LOW])
    else:
        biome = rng.choice(list(SubregionBiome))
        danger_level = rng.choice(list(DangerLevel))

    return SubregionIdentity(
        biome=biome,
        danger_level=danger_level,
        population_density=rng.choice(list(PopulationDensity)),
        culture_summary=rng.choice(SUBREGION_CULTURE_SUMMARIES),
        economy_summary=rng.choice(SUBREGION_ECONOMY_SUMMARIES),
    )


def generate_subregion_geography(
    rng: random.Random, biome: str, used_names: set[str]
) -> tuple[str, str, str]:
    """Picks one major physical geography feature (name, Location.type,
    description) matching a subregion's biome — geography must influence
    placement, not appear at random (Phase 15E spec). Avoids reusing a
    name already claimed elsewhere in the region (two MOUNTAINS
    subregions should not both produce a place called "Muralha de
    Pedra") by falling back to any other biome's unclaimed candidate."""
    own_candidates = [c for c in GEOGRAPHY_BY_BIOME[str(biome)] if c[0] not in used_names]
    if own_candidates:
        chosen = rng.choice(own_candidates)
        used_names.add(chosen[0])
        return chosen

    all_candidates = [c for pool in GEOGRAPHY_BY_BIOME.values() for c in pool if c[0] not in used_names]
    chosen = rng.choice(all_candidates) if all_candidates else rng.choice(GEOGRAPHY_BY_BIOME[str(biome)])
    used_names.add(chosen[0])
    return chosen


def generate_settlement_name(rng: random.Random, used_names: set[str], max_attempts: int = 50) -> str:
    """Combines two syllable pools into a settlement name, retrying on
    collision so a massive region never produces duplicate settlement
    names (Phase 15Q's own "duplicate names where inappropriate" check)."""
    for _ in range(max_attempts):
        name = rng.choice(SETTLEMENT_NAME_PARTS_A) + rng.choice(SETTLEMENT_NAME_PARTS_B)
        if name not in used_names:
            used_names.add(name)
            return name
    # Pool exhausted at this scale — fall back to a numbered variant rather
    # than looping forever or silently persisting a duplicate.
    base = rng.choice(SETTLEMENT_NAME_PARTS_A) + rng.choice(SETTLEMENT_NAME_PARTS_B)
    suffix = 2
    name = f"{base} {suffix}"
    while name in used_names:
        suffix += 1
        name = f"{base} {suffix}"
    used_names.add(name)
    return name


def choose_major_settlement_type(rng: random.Random, biome: str) -> str:
    """Picks a plausible major-settlement type for a subregion's biome —
    settlements should have a reason to exist (Phase 15F spec)."""
    return rng.choice(SETTLEMENT_TYPE_BY_BIOME[str(biome)])


def choose_minor_settlement_type(rng: random.Random) -> str:
    return rng.choice(["VILLAGE", "HAMLET", "ISOLATED_SETTLEMENT"])


def minor_settlement_count(rng: random.Random) -> int:
    low, high = MINOR_SETTLEMENTS_PER_SUBREGION
    return rng.randint(low, high)


def settlement_profile(settlement_type: str) -> str:
    return SETTLEMENT_PROFILE_BY_TYPE[str(settlement_type)]


def settlement_population_tier(settlement_type: str) -> int:
    return POPULATION_TIER_BY_TYPE[str(settlement_type)]


def generate_settlement_services(settlement_type: str) -> list[tuple[str, str, str]]:
    """Returns the (name, Location.type, description) triples for every
    service a settlement of this type has — deterministic by type alone
    (which services exist is a design fact, not a roll), so two
    settlements of the same type always offer the same service set. Not
    every settlement has every service (spec)."""
    keys = SERVICES_BY_SETTLEMENT_TYPE[str(settlement_type)]
    return [SETTLEMENT_SERVICE_POOL[key] for key in keys]


def is_city_scale(settlement_type: str) -> bool:
    return str(settlement_type) in CITY_SCALE_TYPES


def city_districts() -> list[tuple[str, str]]:
    """MAJOR_CITY/CITY settlements are organized into districts (spec) —
    every city gets the same fixed set, since which districts a city has
    is structural, not random."""
    return list(CITY_DISTRICTS)


def generate_subregion_names(rng: random.Random) -> list[str]:
    """Phase 15C — the Region Skeleton's macro subdivision list. Always
    includes the fixed anchor subregion (Campos de Cardal, containing the
    pinned starting village) first, then a seed-driven sample of the rest
    of the pool — a massive Region has many subregions (spec: "8-15"), but
    exactly which ones exist varies per campaign."""
    count = rng.randint(MIN_SUBREGIONS, MAX_SUBREGIONS)
    rest = rng.sample(SUBREGION_NAME_POOL, k=count - 1)
    return [ANCHOR_SUBREGION_NAME, *rest]
