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

from app.game.world.content_pools import (
    ANCHOR_SUBREGION_NAME,
    CLIMATE_SUMMARIES,
    CULTURAL_SUMMARIES,
    HISTORICAL_SUMMARIES,
    SUBREGION_NAME_POOL,
)

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


def generate_subregion_names(rng: random.Random) -> list[str]:
    """Phase 15C — the Region Skeleton's macro subdivision list. Always
    includes the fixed anchor subregion (Campos de Cardal, containing the
    pinned starting village) first, then a seed-driven sample of the rest
    of the pool — a massive Region has many subregions (spec: "8-15"), but
    exactly which ones exist varies per campaign."""
    count = rng.randint(MIN_SUBREGIONS, MAX_SUBREGIONS)
    rest = rng.sample(SUBREGION_NAME_POOL, k=count - 1)
    return [ANCHOR_SUBREGION_NAME, *rest]
