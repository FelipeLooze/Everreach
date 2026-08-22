"""Phase 17N — Information Reliability & Contradiction.

"The system should allow contradictory beliefs. Do NOT automatically
overwrite old knowledge with latest information" (spec) was already
true by construction, not something this subphase needed to add:
- Canonical aspect facts (17A) and rumor facts (17C) about the same
  (entity, aspect) already live as separate KnowledgeFact rows under
  distinct fact_keys — a knower can hold both at once.
- Multiple independent rumors about the same (entity, aspect) already
  coexist (17C, rumor_key namespacing) — Traveler A's "it's safe" and
  the Hunter's "stay away" can both be real KnowledgeKnower rows for
  the same character simultaneously.
- teach_fact (Phase 4/5) never downgrades a knower's certainty, and
  nothing anywhere overwrites one fact's statement with another's.

What was missing: a way to actually SEE the contradiction.
list_known_perspectives gathers every distinct piece of information one
knower currently holds about one aspect — canonical and rumor alike —
so a caller (eventually the Narrator, 17P) can present "here's what you
know, and it doesn't all agree" instead of silently picking one belief
to show. Ordered by certainty (most confidently held first) — spec's
"Direct observation may increase confidence", though even that top
belief may itself be outdated later (17H already covers a map's own
staleness; this module is the read-side view across ALL of one
knower's beliefs, not a truth-arbiter).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType, KnowledgeCertainty
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.game.knowledge.geography import geographic_fact_key, geographic_subject
from app.game.npcs.service import certainty_rank


@dataclass
class KnownPerspective:
    fact_key: str
    statement: str
    certainty: str
    precision: GeographicPrecision | None
    is_rumor: bool
    source: str


def list_known_perspectives(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
) -> list[KnownPerspective]:
    """Every distinct piece of information this exact knower holds
    about this exact aspect, most-confidently-held first."""
    subject = geographic_subject(subject_kind, entity_id)
    canonical_key = geographic_fact_key(subject_kind, entity_id, aspect)
    aspect_prefix = f"{canonical_key}:"

    rows = (
        db.query(KnowledgeFact, KnowledgeKnower)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.subject == subject,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .all()
    )

    perspectives = [
        KnownPerspective(
            fact_key=fact.fact_key,
            statement=fact.statement,
            certainty=knower.certainty,
            precision=GeographicPrecision(knower.precision) if knower.precision else None,
            is_rumor=":rumor:" in fact.fact_key,
            source=knower.source,
        )
        for fact, knower in rows
        if fact.fact_key == canonical_key or fact.fact_key.startswith(aspect_prefix)
    ]

    perspectives.sort(key=lambda p: certainty_rank(KnowledgeCertainty(p.certainty)), reverse=True)
    return perspectives


def has_contradictory_information(perspectives: list[KnownPerspective]) -> bool:
    distinct_statements = {p.statement for p in perspectives}
    return len(distinct_statements) > 1
