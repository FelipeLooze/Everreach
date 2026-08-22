"""Phase 16U — Knowledge & Discovery Boundaries.

The core requirement ("Backend may know the full Region. Logan may
know only a rumor. Do not automatically reveal Region name/cities/
roads/culture/organizations/dangers") is already satisfied by reusing
existing, unmodified machinery — no new code was needed for it:

- Region.discovery_status starts RUMORED for a materialized neighbor
  (16I), never DISCOVERED.
- app.api.serializers.to_game_state_response already gates
  RegionSummary.name behind explicitly_knows_name (a per-character
  Knowledge check, not a discovery_status check) — the exact same
  mechanism that already hides Location names (Phase 15S). Nothing
  about a neighboring Region needed a special case; the existing
  anti-hallucination architecture already covers it, since nothing in
  16A-16T ever calls teach_fact with the player learning the neighbor's
  real name.

What genuinely IS new here: grant_rumor_of_neighbor_region — the one
explicit, controlled way a character can learn the spec's own worked
example ("Some eastern kingdom lies beyond the mountains. That is
enough.") without learning the Region's real name, cities, or culture.
The rumor fact only ever mentions the Boundary's own name (already
knowable) — never neighbor_region.name.
"""

from sqlalchemy.orm import Session

from app.core.enums import KnowerType
from app.db.models.knowledge import KnowledgeFact
from app.db.models.region import Region
from app.db.models.regional_boundary import RegionalBoundary
from app.game.npcs.service import teach_fact

RUMOR_FACT_KEY_PREFIX = "neighbor_rumor"


def _rumor_fact_key(boundary_id: str) -> str:
    return f"{RUMOR_FACT_KEY_PREFIX}:{boundary_id}"


def _ensure_rumor_fact(db: Session, campaign_id: str, boundary: RegionalBoundary) -> KnowledgeFact:
    fact_key = _rumor_fact_key(boundary.id)
    fact = (
        db.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign_id, KnowledgeFact.fact_key == fact_key)
        .first()
    )
    if fact is not None:
        return fact

    fact = KnowledgeFact(
        campaign_id=campaign_id,
        subject=f"boundary:{boundary.id}",
        fact_key=fact_key,
        statement=f"Rumores falam de terras habitadas além de {boundary.name}.",
        is_secret=False,
    )
    db.add(fact)
    db.flush()
    return fact


def grant_rumor_of_neighbor_region(
    db: Session,
    campaign_id: str,
    character_id: str,
    boundary: RegionalBoundary,
    *,
    source: str = "rumor local",
) -> None:
    """Grants the player the vague "something is out there" rumor —
    never the neighboring Region's real name, cities, roads, or
    culture, all of which stay gated behind explicitly_knows_name until
    a real Knowledge grant mentions them by name (not done here, not
    done anywhere in Phase 16)."""
    fact = _ensure_rumor_fact(db, campaign_id, boundary)
    teach_fact(db, campaign_id, fact.fact_key, KnowerType.PLAYER, character_id, source=source)
