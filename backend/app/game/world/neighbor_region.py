"""Phase 16I/16J/16K/16L/16M/16N/16O — Macro Geography Generation through
Threats & Ecology for a neighboring Region.

materialize_neighbor_region generates a full massive Region — the exact
same scale and pipeline as the starting Region (app.game.world.seed),
reusing app.game.world.region_content.generate_region_settlements_and_infrastructure
wholesale rather than a parallel generator. This single call already
satisfies several of Phase 16's subphases simultaneously, because they
turned out to be genuinely inseparable once the shared pipeline existed
(see the 16I commit message for the honest breakdown of which subphase
gets what from this one function):

- 16K (Subregion Generation): reuses generate_subregion_names/
  generate_subregion_identity exactly as the starting Region does.
- 16L (Settlement Network): reuses the shared pipeline's settlement/
  district/service generation, which is already environment-driven
  (SETTLEMENT_TYPE_BY_BIOME) — a coastal neighbor gets port-appropriate
  settlements the same way the starting Region's own subregions do.
- 16M (Organizations & Political Structure): reuses the shared
  pipeline's one-organization-per-major-settlement generation.
- 16N (Economy & Trade Relations): reuses the shared pipeline's wealth
  band + export good baseline. Actual cross-region trade *relationships*
  stay a documented gap — see NeighborRegionConstraints.known_imported_goods,
  deliberately empty until this subphase's own economy-linkage step
  exists for real (not invented here as placeholder prose).
- 16O (Threats & Ecology): reuses the shared pipeline's one-threat-per-
  subregion generation.

What IS new in this module, not just reused:
- 16I itself: the orchestration that calls all of the above for a
  *second* Region, keyed by region_index rather than always "region:0".
- 16J (Regional Identity & Culture): honors 16H's
  NeighborRegionConstraints by (a) forcing the neighbor's own first
  subregion's biome to plausibly continue the boundary's terrain
  (forced_biome — geography doesn't just stop at the border) and (b)
  weaving known_historical_relationship into the generated
  historical_summary, so a documented political tension at the boundary
  shows up in the neighbor's own history text instead of being silently
  dropped.

Deliberately NOT done here (later subphases): destination_region_id on
the RegionalBoundary, the actual cross-Region LocationConnection pair
(16Q), independent validation beyond what validate_region_package
already does (16R), and transactional persistence tied to
RegionMaterializationRequest fulfillment (16S).
"""

import random

from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus
from app.db.models.campaign import Campaign
from app.db.models.region import Region
from app.db.models.location import Location
from app.db.models.regional_boundary import RegionalBoundary
from app.db.models.subregion import Subregion
from app.game.world.generation import CURRENT_REGION_GENERATION_VERSION, derive_seed
from app.game.world.generator import (
    generate_region_identity,
    generate_region_name,
    generate_subregion_identity,
    generate_subregion_names_for_neighbor_region,
)
from app.game.world.cross_region_canon import record_cross_region_historical_relationship
from app.game.world.neighbor_constraints import build_neighbor_region_constraints
from app.game.world.region_content import generate_region_settlements_and_infrastructure
from app.game.world.validation import validate_region_package

NEIGHBOR_REGION_DESCRIPTION = (
    "Um vasto território além da fronteira, cuja extensão real ainda escapa "
    "ao conhecimento de quem vive do outro lado."
)


def materialize_neighbor_region(
    db: Session,
    campaign_id: str,
    boundary: RegionalBoundary,
    region_index: int,
) -> Region:
    """Generates and persists (but does not yet validate transactionally,
    connect across the boundary, or mark any request fulfilled — see
    module docstring) a full neighboring Region on the far side of
    boundary."""
    campaign = db.get(Campaign, campaign_id)
    region_seed = derive_seed(campaign.world_seed, f"region:{region_index}")

    constraints = build_neighbor_region_constraints(db, boundary)

    identity_rng = random.Random(derive_seed(region_seed, "identity"))
    climate_summary, cultural_summary, historical_summary = generate_region_identity(identity_rng)
    if constraints.known_historical_relationship:
        historical_summary = f"{historical_summary} {constraints.known_historical_relationship}"

    region_name = generate_region_name(random.Random(derive_seed(region_seed, "region_name")))

    region = Region(
        campaign_id=campaign_id,
        name=region_name,
        description=NEIGHBOR_REGION_DESCRIPTION,
        # 16U — the backend knows this Region in full the moment it's
        # generated, but nobody on the near side has actually been
        # there. RUMORED (not UNKNOWN): the boundary's own publicly
        # known routes already imply *something* is known to exist
        # beyond it (spec's "Logan may know: some eastern kingdom lies
        # beyond the mountains").
        discovery_status=DiscoveryStatus.RUMORED,
        generation_seed=region_seed,
        generation_version=CURRENT_REGION_GENERATION_VERSION,
        climate_summary=climate_summary,
        cultural_summary=cultural_summary,
        historical_summary=historical_summary,
    )
    db.add(region)
    db.flush()

    anchor_subregion = db.get(Subregion, boundary.anchor_subregion_id)

    # Campaign-wide, not region-scoped: the content pools generation
    # draws from (subregion names, geography/settlement/POI names) are
    # finite and shared across every Region in the campaign, so a second
    # Region's own generation must know what the first one already
    # claimed, or the two can collide (a real, previously-untested
    # scenario — only ever mattered once a second Region could exist,
    # same root cause as the validate_region_package fix in 16I).
    used_subregion_names = {
        row[0]
        for row in db.query(Subregion.name).join(Region, Subregion.region_id == Region.id).filter(
            Region.campaign_id == campaign_id
        ).all()
    }
    used_location_names = {
        row[0]
        for row in db.query(Location.name).join(Region, Location.region_id == Region.id).filter(
            Region.campaign_id == campaign_id
        ).all()
    }

    subregion_rng = random.Random(derive_seed(region_seed, "subregions"))
    subregion_names = generate_subregion_names_for_neighbor_region(subregion_rng, used_subregion_names)
    subregions = []
    for index, name in enumerate(subregion_names):
        subregion_seed = derive_seed(region_seed, f"subregion:{index}")
        identity = generate_subregion_identity(
            random.Random(derive_seed(subregion_seed, "identity")),
            forced_biome=(anchor_subregion.biome if index == 0 else None),
        )
        subregions.append(
            Subregion(
                region_id=region.id,
                name=name,
                order_index=index,
                generation_seed=subregion_seed,
                **identity,
            )
        )
    db.add_all(subregions)
    db.flush()
    region.skeleton_complete = True

    used_npc_names: set[str] = set()
    generate_region_settlements_and_infrastructure(
        db, campaign_id, region, region_seed, subregions,
        used_location_names, used_npc_names, entry_location=None,
    )

    validate_region_package(db, region)

    source_region = db.get(Region, boundary.source_region_id)
    record_cross_region_historical_relationship(db, campaign_id, source_region, region, constraints)

    return region
