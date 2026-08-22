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

from app.db.models.location import Location, LocationConnection, LocationFeature
from app.db.models.settlement import Settlement
from app.game.world.content_pools import MINOR_SETTLEMENT_FEATURES
from app.game.world.generator import (
    interior_description_for_service,
    materialize_minor_settlement_description,
    settlement_population_tier,
    settlement_profile,
)

MINOR_SETTLEMENT_TYPES = ("village", "hamlet", "isolated_settlement")
INTERIOR_ELIGIBLE_SERVICE_TYPES = ("inn", "tavern", "blacksmith", "shop", "temple", "warehouse")


def ensure_location_materialized(db: Session, location: Location) -> Location:
    """Fills in detail for an already-existing but not-yet-detailed
    Location. Tier 2 (Phase 15F minor settlement stubs) get filled in and
    flip to Tier 1. Already-Tier-1 service locations (Phase 15G inn/
    tavern/blacksmith/...) get a Tier 3 interior child materialized
    alongside them, if one doesn't already exist. Anything else is
    returned unchanged."""
    if location.materialization_tier == 2 and location.type in MINOR_SETTLEMENT_TYPES:
        _materialize_minor_settlement(db, location)
        location.materialization_tier = 1
        db.flush()
        return location

    if location.materialization_tier == 1 and location.type in INTERIOR_ELIGIBLE_SERVICE_TYPES:
        _ensure_interior(db, location)

    return location


def _ensure_interior(db: Session, service_location: Location) -> Location | None:
    existing = (
        db.query(Location)
        .filter(Location.parent_location_id == service_location.id, Location.materialization_tier == 3)
        .first()
    )
    if existing is not None:
        return existing

    description = interior_description_for_service(service_location.type)
    if description is None:
        return None

    interior = Location(
        region_id=service_location.region_id,
        subregion_id=service_location.subregion_id,
        parent_location_id=service_location.id,
        name=f"Interior de {service_location.name}",
        type="interior",
        description=description,
        discovery_status=service_location.discovery_status,
        materialization_tier=3,
    )
    db.add(interior)
    db.flush()
    db.add(
        LocationConnection(
            from_location_id=service_location.id,
            to_location_id=interior.id,
            direction="dentro",
            connection_type="PATH",
            distance=0.1,
            danger=0,
        )
    )
    db.add(
        LocationConnection(
            from_location_id=interior.id,
            to_location_id=service_location.id,
            direction="fora",
            connection_type="PATH",
            distance=0.1,
            danger=0,
        )
    )
    db.flush()
    return interior


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
