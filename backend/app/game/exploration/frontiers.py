"""Phase 17J — Frontiers.

A Frontier is not "edge of the generated map" (spec) — it's never
stored as a status on a Subregion at all, since that would immediately
violate the spec's own "FRONTIERS ARE RELATIVE" and "FRONTIER CHANGE"
rules: a fixed field can't be simultaneously "homeland to the native
community, frontier to the kingdom" nor evolve as knowledge/settlement
spreads without a background job constantly rewriting it. Instead,
frontier-ness is always derived, fresh, from two things that already
exist and already change on their own:

- Subregion.population_density (Phase 15D) — how settled a place
  actually is, world-truth, the same for everyone.
- known_geographic_aspects (17A) for the querying knower — how much
  THIS knower specifically knows about it.

The same Subregion is frontier territory to a knower with sparse
knowledge and homeland to one who knows it well — no separate
computation needed per perspective beyond calling this with a different
knower_type/knower_id (spec's Hunter/Kingdom example, made literal).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import KnowerType, PopulationDensity
from app.db.models.subregion import Subregion
from app.game.knowledge.geography import known_geographic_aspects

_SPARSE_DENSITIES = (PopulationDensity.SPARSE, PopulationDensity.LOW)
_FAMILIARITY_THRESHOLD = 2


@dataclass
class FrontierAssessment:
    subregion_id: str
    is_frontier: bool
    sparse_settlement: bool
    known_aspect_count: int


def assess_frontier_status(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subregion: Subregion,
) -> FrontierAssessment:
    sparse = PopulationDensity(subregion.population_density) in _SPARSE_DENSITIES
    known = known_geographic_aspects(db, campaign_id, knower_type, knower_id, "subregion", subregion.id)
    unfamiliar = len(known) < _FAMILIARITY_THRESHOLD

    return FrontierAssessment(
        subregion_id=subregion.id,
        is_frontier=sparse and unfamiliar,
        sparse_settlement=sparse,
        known_aspect_count=len(known),
    )
