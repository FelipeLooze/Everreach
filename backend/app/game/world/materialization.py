"""Phase 15N/15O/15P — Content-on-Demand.

Deep materialization adds detail to an already-existing part of the
world; it never answers "what exists here?" from nothing (spec's own
"CRITICAL CONTENT-ON-DEMAND RULE"). Every function here operates on a
Location that Phase 15's bulk generation (app.game.world.seed) already
persisted as a Tier 2 stub (materialization_tier=2, see Phase 15F) — it
only fills in detail and flips the tier, once, permanently (Phase 15
spec's own "GENERATION VERSIONING": never silently regenerate).

The protagonist is not the only trigger (spec's "SIMULATION-DRIVEN
MATERIALIZATION") — ensure_location_materialized is safe to call from
anywhere (travel, NPC/simulation code, a future world event) since it is
idempotent: a Tier 1 location is returned unchanged.
"""

import random

from sqlalchemy.orm import Session

from app.db.models.location import Location, LocationFeature
from app.db.models.settlement import Settlement
from app.game.world.content_pools import MINOR_SETTLEMENT_FEATURES
from app.game.world.generator import (
    materialize_minor_settlement_description,
    settlement_population_tier,
    settlement_profile,
)

MINOR_SETTLEMENT_TYPES = ("village", "hamlet", "isolated_settlement")


def ensure_location_materialized(db: Session, location: Location) -> Location:
    """Fills in detail for a Tier 2 stub Location, then marks it Tier 1.
    A no-op for anything already Tier 1 (or Tier 3 — interiors are
    Phase 15O's own, separate concern)."""
    if location.materialization_tier != 2:
        return location

    if location.type in MINOR_SETTLEMENT_TYPES:
        _materialize_minor_settlement(db, location)

    location.materialization_tier = 1
    db.flush()
    return location


def _materialize_minor_settlement(db: Session, location: Location) -> None:
    rng = random.Random(location.id)
    description = materialize_minor_settlement_description(rng)
    location.description = description

    feature_name, feature_description = rng.choice(MINOR_SETTLEMENT_FEATURES)
    db.add(
        LocationFeature(
            location_id=location.id,
            name=feature_name,
            description=feature_description,
        )
    )

    existing_settlement = (
        db.query(Settlement).filter(Settlement.location_id == location.id).first()
    )
    if existing_settlement is None:
        settlement_type = location.type.upper()
        db.add(
            Settlement(
                location_id=location.id,
                settlement_type=settlement_type,
                profile=settlement_profile(settlement_type),
                population_tier=settlement_population_tier(settlement_type),
            )
        )
