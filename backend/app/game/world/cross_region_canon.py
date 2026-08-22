"""Phase 16P — Historical / Canon Relationships.

The neighboring Region's historical_summary already gained a sentence
about the boundary's documented political tension (16I/16J). That's
prose on a display field, not a queryable fact anything else in the
game can reason about (an NPC line, a future quest hook, the narrator's
own anti-hallucination context). This module makes the SAME relationship
a real KnowledgeFact instead, reusing the Knowledge system exactly like
every other piece of world truth in Everreach — never a new "canon
relationship" table.

Only ever derived from what 16H's constraints already established (the
boundary's own barriers/routes) — never invented independently, so the
Region Generator can't "rewrite established history" (spec).
"""

from sqlalchemy.orm import Session

from app.db.models.knowledge import KnowledgeFact
from app.db.models.region import Region
from app.game.world.neighbor_constraints import NeighborRegionConstraints


def record_cross_region_historical_relationship(
    db: Session,
    campaign_id: str,
    source_region: Region,
    neighbor_region: Region,
    constraints: NeighborRegionConstraints,
) -> KnowledgeFact:
    """World truth only — nobody is granted this fact here (16U governs
    who, if anyone, actually knows it)."""
    fact_key = f"region_relationship:{source_region.id}:{neighbor_region.id}"
    statement = (
        f"{constraints.known_historical_relationship} "
        f"({source_region.name} e o território além de {constraints.required_geography})."
    )
    fact = KnowledgeFact(
        campaign_id=campaign_id,
        subject=f"region:{neighbor_region.id}",
        fact_key=fact_key,
        statement=statement,
        is_secret=False,
    )
    db.add(fact)
    db.flush()
    return fact
