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

from app.core.enums import BoundaryBarrierCategory, DangerLevel, PopulationDensity, SubregionBiome, ThreatIntensity
from app.game.world.content_pools import (
    ANCHOR_CLEARING_OPTIONS,
    ANCHOR_FOREST_OPTIONS,
    ANCHOR_RIVER_OPTIONS,
    ANCHOR_ROAD_OPTIONS,
    ANCHOR_SUBREGION_NAME_POOL,
    BLACKSMITH_FLAVOR_OPTIONS,
    CITY_DISTRICTS,
    CLIMATE_SUMMARIES,
    CLIMATIC_BARRIER_POOL,
    CULTURAL_SUMMARIES,
    ECOLOGICAL_BARRIER_POOL,
    GEOGRAPHICAL_BARRIER_HAZARDS_BY_BIOME,
    LOGISTICAL_BARRIER_POOL,
    POLITICAL_BARRIER_POOL,
    ROUTE_TERM_BY_BIOME,
    ELDER_FLAVOR_OPTIONS,
    EXPORT_GOOD_BY_SETTLEMENT_TYPE,
    GEOGRAPHY_BY_BIOME,
    HISTORICAL_SUMMARIES,
    INNKEEPER_FLAVOR_OPTIONS,
    INTERIOR_DESCRIPTION_BY_SERVICE_TYPE,
    LEADER_BACKSTORY_POOL,
    LEADER_PERSONALITY_POOL,
    REGION_NAME_POOL,
    LEADER_TITLE_BY_ORG_TYPE,
    MINOR_SETTLEMENT_DESCRIPTIONS,
    NPC_FAMILY_NAME_POOL,
    NPC_GIVEN_NAME_POOL,
    ORG_NAME_TEMPLATE_BY_TYPE,
    ORG_TYPE_BY_SETTLEMENT_TYPE,
    POI_POOL,
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
    THREAT_POOL,
    WEALTH_BAND_BY_SETTLEMENT_TYPE,
)

DANGER_LEVEL_TO_THREAT_INTENSITY = {
    "SAFE": ThreatIntensity.LOW,
    "LOW": ThreatIntensity.LOW,
    "MODERATE": ThreatIntensity.MODERATE,
    "HIGH": ThreatIntensity.HIGH,
    "SEVERE": ThreatIntensity.HIGH,
}

EXPORT_SUPPLY_BONUS = 80

CITY_SCALE_TYPES = ("MAJOR_CITY", "CITY")

# Phase 15H — Roads, Routes & Connections. Distance is in the same unit
# app.game.travel.service already uses (BASE_MINUTES_PER_DISTANCE=15
# minutes per unit at normal pace/speed) — never a new travel mechanic,
# just data at a scale that makes crossing the region actually take days.
INTER_SUBREGION_DISTANCE_RANGE = (80.0, 300.0)  # ~20-75 hours per hop
LOCAL_DISTANCE_RANGE = (0.5, 2.5)  # same scale as the original hand-authored Cardal connections
HARSH_TRAVEL_BIOMES = ("MOUNTAINS", "WETLANDS")

DANGER_LEVEL_TO_CONNECTION_DANGER = {
    "SAFE": 0,
    "LOW": 1,
    "MODERATE": 3,
    "HIGH": 6,
    "SEVERE": 10,
}

COMPASS_DIRECTION_PAIRS = [
    ("norte", "sul"),
    ("sul", "norte"),
    ("leste", "oeste"),
    ("oeste", "leste"),
    ("nordeste", "sudoeste"),
    ("sudoeste", "nordeste"),
    ("noroeste", "sudeste"),
    ("sudeste", "noroeste"),
]


def danger_level_to_connection_danger(danger_level: str) -> int:
    return DANGER_LEVEL_TO_CONNECTION_DANGER[str(danger_level)]


def travel_time_modifier_for_biome(biome: str) -> float:
    return 1.3 if str(biome) in HARSH_TRAVEL_BIOMES else 1.0


def roll_inter_subregion_distance(rng: random.Random) -> float:
    low, high = INTER_SUBREGION_DISTANCE_RANGE
    return round(rng.uniform(low, high), 1)


def roll_local_distance(rng: random.Random) -> float:
    low, high = LOCAL_DISTANCE_RANGE
    return round(rng.uniform(low, high), 1)


def roll_compass_direction_pair(rng: random.Random) -> tuple[str, str]:
    return rng.choice(COMPASS_DIRECTION_PAIRS)


# Phase 15I — Major Points of Interest. Deliberately remote: farther and
# more dangerous than the settlement-local connections from Phase 15G/15H.
POI_DISTANCE_RANGE = (1.5, 4.0)
POI_COUNT_RANGE = (1, 2)
POI_DANGER_BONUS = 2


def generate_pois(rng: random.Random, used_names: set[str]) -> list[tuple[str, str, str]]:
    """Picks 1-2 major POIs for a subregion, never reusing a name already
    claimed elsewhere in the region (same discipline as settlements and
    geography — Phase 15Q's own "duplicate names" check). The pool (9
    archetypes) is smaller than a massive region's total POI demand, so
    once every archetype name is claimed, later ones fall back to a
    numbered variant rather than silently repeating a name or running
    dry (same discipline as generate_settlement_name)."""
    low, high = POI_COUNT_RANGE
    count = rng.randint(low, high)
    chosen = []
    for _ in range(count):
        available = [poi for poi in POI_POOL if poi[0] not in used_names]
        if available:
            name, poi_type, description = rng.choice(available)
        else:
            base_name, poi_type, description = rng.choice(POI_POOL)
            suffix = 2
            name = f"{base_name} {suffix}"
            while name in used_names:
                suffix += 1
                name = f"{base_name} {suffix}"
        used_names.add(name)
        chosen.append((name, poi_type, description))
    return chosen


def roll_poi_distance(rng: random.Random) -> float:
    low, high = POI_DISTANCE_RANGE
    return round(rng.uniform(low, high), 1)


def poi_connection_danger(subregion_danger_level: str) -> int:
    return danger_level_to_connection_danger(subregion_danger_level) + POI_DANGER_BONUS


# Phase 15J — Regional Organizations & Major NPCs.
def organization_type_for_settlement(settlement_type: str) -> str:
    return ORG_TYPE_BY_SETTLEMENT_TYPE[str(settlement_type)]


def organization_name_for_settlement(settlement_name: str, organization_type: str) -> str:
    template = ORG_NAME_TEMPLATE_BY_TYPE[str(organization_type)]
    return template.format(name=settlement_name)


def leader_title_for_organization(organization_type: str) -> str:
    return LEADER_TITLE_BY_ORG_TYPE[str(organization_type)]


def generate_npc_name(rng: random.Random, used_names: set[str], max_attempts: int = 30) -> str:
    """Combines given+family name pools, retrying on collision — same
    discipline as generate_settlement_name, distinct pools so NPCs never
    read like place names."""
    for _ in range(max_attempts):
        name = f"{rng.choice(NPC_GIVEN_NAME_POOL)} {rng.choice(NPC_FAMILY_NAME_POOL)}"
        if name not in used_names:
            used_names.add(name)
            return name
    suffix = 2
    base = f"{rng.choice(NPC_GIVEN_NAME_POOL)} {rng.choice(NPC_FAMILY_NAME_POOL)}"
    name = f"{base} {suffix}"
    while name in used_names:
        suffix += 1
        name = f"{base} {suffix}"
    used_names.add(name)
    return name


def generate_leader_flavor(rng: random.Random) -> tuple[str, str]:
    """Returns (personality, backstory) for a settlement/organization leader."""
    return rng.choice(LEADER_PERSONALITY_POOL), rng.choice(LEADER_BACKSTORY_POOL)


# Phase 15K — Regional Economy Baseline.
def wealth_band_for_settlement(settlement_type: str) -> str:
    return WEALTH_BAND_BY_SETTLEMENT_TYPE[str(settlement_type)]


def export_good_for_settlement(settlement_type: str) -> str | None:
    return EXPORT_GOOD_BY_SETTLEMENT_TYPE[str(settlement_type)]


# Phase 15L — Regional Threats, Wildlife & Ecology.
def threat_intensity_for_danger_level(danger_level: str) -> str:
    """Derived from the subregion's own DangerLevel (Phase 15D) — never
    an independent roll — so a subregion's ecology stays consistent with
    how dangerous it was already established to be."""
    return DANGER_LEVEL_TO_THREAT_INTENSITY[str(danger_level)]


def generate_threat(rng: random.Random) -> tuple[str, str]:
    """Picks one (threat_type, description) for a subregion. Deliberately
    just one per subregion — a population/habitat abstraction, not
    individual creature instances (spec)."""
    return rng.choice(THREAT_POOL)


def materialize_minor_settlement_description(rng: random.Random) -> str:
    """Phase 15N — deep materialization of a Tier 2 minor settlement stub
    (see app.game.world.materialization.ensure_location_materialized)."""
    return rng.choice(MINOR_SETTLEMENT_DESCRIPTIONS)


def interior_description_for_service(service_type: str) -> str | None:
    """Phase 15O — None means this service type has no distinct interior
    concept (e.g. an open-air market square)."""
    return INTERIOR_DESCRIPTION_BY_SERVICE_TYPE.get(str(service_type))


# Phase 16C — Boundary Barriers. Independent per-category roll chance —
# GEOGRAPHICAL always applies (the terrain itself is always a factor),
# the rest combine probabilistically so most boundaries end up with 1-3
# barriers total, never a single arbitrary difficulty number (spec).
# MAGICAL is deliberately never rolled here — see content_pools.py's
# MAGICAL_BARRIER_POOL docstring.
_BARRIER_ROLL_CHANCE = {
    BoundaryBarrierCategory.CLIMATIC: 0.5,
    BoundaryBarrierCategory.ECOLOGICAL: 0.35,
    BoundaryBarrierCategory.POLITICAL: 0.25,
    BoundaryBarrierCategory.LOGISTICAL: 0.2,
}
_BARRIER_POOL_BY_CATEGORY = {
    BoundaryBarrierCategory.CLIMATIC: CLIMATIC_BARRIER_POOL,
    BoundaryBarrierCategory.ECOLOGICAL: ECOLOGICAL_BARRIER_POOL,
    BoundaryBarrierCategory.POLITICAL: POLITICAL_BARRIER_POOL,
    BoundaryBarrierCategory.LOGISTICAL: LOGISTICAL_BARRIER_POOL,
}


def generate_boundary_barriers(rng: random.Random, biome: str) -> list[tuple[str, str, str]]:
    """Returns [(category, name, description), ...] for one
    RegionalBoundary. Always includes one GEOGRAPHICAL barrier flavored
    by the anchor subregion's own biome; other categories combine in
    probabilistically (spec's "COMBINED BARRIERS: prefer believable
    combinations")."""
    geo_name, geo_description = rng.choice(
        GEOGRAPHICAL_BARRIER_HAZARDS_BY_BIOME.get(
            str(biome), GEOGRAPHICAL_BARRIER_HAZARDS_BY_BIOME["FRONTIER"]
        )
    )
    barriers = [(BoundaryBarrierCategory.GEOGRAPHICAL.value, geo_name, geo_description)]

    for category, chance in _BARRIER_ROLL_CHANCE.items():
        if rng.random() < chance:
            name, description = rng.choice(_BARRIER_POOL_BY_CATEGORY[category])
            barriers.append((category.value, name, description))

    return barriers


# Phase 16D — Cross-Region Routes. Two archetypes always exist (spec's
# "NO SINGLE REQUIRED ROUTE" — a boundary must offer real tradeoffs, not
# one path), a third (hidden, uncertain) exists only sometimes. Distance
# is on the same scale as inter-subregion road distance (Phase 15H), but
# longer — crossing a Boundary is a bigger journey than crossing a
# subregion.
BOUNDARY_ROUTE_LONG_DISTANCE_RANGE = (250.0, 500.0)
BOUNDARY_ROUTE_SHORT_DISTANCE_RANGE = (120.0, 250.0)
HIDDEN_ROUTE_CHANCE = 0.4


def generate_boundary_routes(
    rng: random.Random, biome: str, used_names: set[str]
) -> list[dict]:
    """Returns a list of route dicts (name, description, terrain,
    estimated_distance, danger_hint, political_control,
    is_publicly_known) for one RegionalBoundary. Always at least 2
    routes with genuinely different tradeoffs; a third, hidden one
    exists about 40% of the time."""
    terms = ROUTE_TERM_BY_BIOME.get(str(biome), ROUTE_TERM_BY_BIOME["FRONTIER"])
    base_danger = danger_level_to_connection_danger(DangerLevel.MODERATE)

    def named(term: str) -> str:
        place = generate_settlement_name(rng, used_names)
        return f"{term} de {place}"

    routes = [
        {
            "name": named(rng.choice(terms)),
            "description": "A rota mais longa, mas também a mais conhecida e a mais segura entre as opções.",
            "terrain": str(biome),
            "estimated_distance": round(rng.uniform(*BOUNDARY_ROUTE_LONG_DISTANCE_RANGE), 1),
            "danger_hint": base_danger + 1,
            "political_control": "Controlada por um posto ou guarnição local.",
            "is_publicly_known": True,
        },
        {
            "name": named(rng.choice(terms)),
            "description": "Uma rota bem mais curta, mas conhecida por sua reputação perigosa.",
            "terrain": str(biome),
            "estimated_distance": round(rng.uniform(*BOUNDARY_ROUTE_SHORT_DISTANCE_RANGE), 1),
            "danger_hint": base_danger + 5,
            "political_control": "",
            "is_publicly_known": True,
        },
    ]

    if rng.random() < HIDDEN_ROUTE_CHANCE:
        routes.append(
            {
                "name": named(rng.choice(terms)),
                "description": "Uma passagem quase esquecida, mencionada apenas em relatos antigos e incertos.",
                "terrain": str(biome),
                "estimated_distance": round(rng.uniform(*BOUNDARY_ROUTE_SHORT_DISTANCE_RANGE), 1),
                "danger_hint": rng.randint(base_danger, base_danger + 8),
                "political_control": "",
                "is_publicly_known": False,
            }
        )

    return routes


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
    """Phase 15C — the Region Skeleton's macro subdivision list. The
    anchor subregion (index 0, containing the starting settlement) always
    comes first, but its name — like every other subregion's — is picked
    per campaign, not fixed (Phase 15 follow-up). A massive Region has
    many subregions (spec: "8-15"), varying per campaign."""
    count = rng.randint(MIN_SUBREGIONS, MAX_SUBREGIONS)
    anchor_name = rng.choice(ANCHOR_SUBREGION_NAME_POOL)
    rest = rng.sample(SUBREGION_NAME_POOL, k=count - 1)
    return [anchor_name, *rest]


def generate_region_name(rng: random.Random) -> str:
    """Phase 15 follow-up — the Region's own name is generated per
    campaign, same discipline as everything else in Phase 15 (no proper
    noun in Everreach's starting point is fixed anymore)."""
    return rng.choice(REGION_NAME_POOL)


def generate_anchor_flavor_location(rng: random.Random, kind: str) -> tuple[str, str]:
    """Phase 15 follow-up — the starting settlement's 4 hand-authored
    flavor locations (forest/road/river/clearing) keep their original
    shape but pick their name+description from a small per-kind pool
    instead of being one fixed string forever."""
    pool = {
        "forest": ANCHOR_FOREST_OPTIONS,
        "road": ANCHOR_ROAD_OPTIONS,
        "river": ANCHOR_RIVER_OPTIONS,
        "clearing": ANCHOR_CLEARING_OPTIONS,
    }[kind]
    return rng.choice(pool)


def generate_elder_flavor(rng: random.Random, village_name: str) -> tuple[str, str]:
    personality, backstory_template = rng.choice(ELDER_FLAVOR_OPTIONS)
    return personality, backstory_template.format(village=village_name)


def generate_blacksmith_flavor(rng: random.Random) -> tuple[str, str]:
    return rng.choice(BLACKSMITH_FLAVOR_OPTIONS)


def generate_innkeeper_flavor(rng: random.Random, village_name: str) -> tuple[str, str]:
    personality, backstory_template = rng.choice(INNKEEPER_FLAVOR_OPTIONS)
    return personality, backstory_template.format(village=village_name)
