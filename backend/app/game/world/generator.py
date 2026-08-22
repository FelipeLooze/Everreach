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
    CLIMATE_SUMMARIES,
    CULTURAL_SUMMARIES,
    HISTORICAL_SUMMARIES,
)


def generate_region_identity(rng: random.Random) -> tuple[str, str, str]:
    """Picks (climate_summary, cultural_summary, historical_summary) for a
    Region from the curated pools, deterministically for a given rng."""
    return (
        rng.choice(CLIMATE_SUMMARIES),
        rng.choice(CULTURAL_SUMMARIES),
        rng.choice(HISTORICAL_SUMMARIES),
    )
