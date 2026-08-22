"""Phase 17M — Shared Geographic Knowledge.

"No omniscient transfer" (spec) is already fully solved by
app.game.npcs.service.propagate_fact/propagate_fact_locally (Phase
4/5): they raise if the source doesn't actually know the fact, they
never overwrite a target's higher-ranked certainty, and every transfer
is explicit — narrative prose can never call this implicitly. Reused
here wholesale, not reimplemented.

What propagate_fact does NOT know about is precision (17B) — it's a
generic Knowledge primitive, unaware that some facts carry a
"how detailed" dimension at all. propagate_geographic_knowledge is the
thin, geography-specific layer on top: it calls propagate_fact for the
certainty/existence transfer, then degrades precision by one step by
default — "shared information can degrade" (spec's own example: an NPC
who knows a route PRECISELY, explaining it verbally, teaches Logan
something closer to APPROXIMATE, not the same precision they hold).
Pass degrade_precision=False for a channel that preserves detail (a
physical map handed over, 17G — "A physical map may communicate better
information" per spec) instead of guessing at a whole linguistic
information-loss model (explicitly out of scope: "Do not build a
linguistic information-loss simulator").
"""

from sqlalchemy.orm import Session

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.game.knowledge.geography import geographic_fact_key, geographic_knowledge_precision, precision_rank
from app.game.npcs.service import propagate_fact, propagate_fact_locally

_DEGRADE_ONE_STEP = {
    GeographicPrecision.PRECISE: GeographicPrecision.GOOD,
    GeographicPrecision.GOOD: GeographicPrecision.APPROXIMATE,
    GeographicPrecision.APPROXIMATE: GeographicPrecision.VAGUE,
    GeographicPrecision.VAGUE: GeographicPrecision.VAGUE,
}


def _apply_target_precision(
    db: Session, campaign_id: str, fact_key: str, knower_type: KnowerType, knower_id: str, precision: GeographicPrecision
) -> None:
    fact = db.query(KnowledgeFact).filter(KnowledgeFact.campaign_id == campaign_id, KnowledgeFact.fact_key == fact_key).one()
    knower = (
        db.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .one()
    )
    current = GeographicPrecision(knower.precision) if knower.precision else None
    if current is None or precision_rank(precision) > precision_rank(current):
        knower.precision = precision.value
        db.flush()


def propagate_geographic_knowledge(
    db: Session,
    campaign_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
    from_type: KnowerType,
    from_id: str,
    to_type: KnowerType,
    to_id: str,
    *,
    degrade_precision: bool = True,
    require_same_location: bool = False,
) -> bool:
    """Returns False (nothing changed) if the target already knew this
    at an equal or higher certainty rank — same "no wasted redundant
    transfer" contract as propagate_fact itself."""
    fact_key = geographic_fact_key(subject_kind, entity_id, aspect)
    source_precision = geographic_knowledge_precision(db, campaign_id, from_type, from_id, subject_kind, entity_id, aspect)

    transfer = propagate_fact_locally if require_same_location else propagate_fact
    propagated = transfer(db, campaign_id, fact_key, from_type, from_id, to_type, to_id)
    if not propagated:
        return False

    if source_precision is not None:
        target_precision = _DEGRADE_ONE_STEP[source_precision] if degrade_precision else source_precision
        _apply_target_precision(db, campaign_id, fact_key, to_type, to_id, target_precision)

    return True
