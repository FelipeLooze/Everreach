"""Phase 17A — Geographic Knowledge Foundation.

WORLD EXISTS != CHARACTER KNOWS WORLD. This module adds no new tables,
no new columns, no parallel "exploration knowledge" system — it is a
thin, deliberately small convention layer over the existing
KnowledgeFact/KnowledgeKnower machinery (app.db.models.knowledge,
app.game.npcs.service.teach_fact/knows), the same machinery every prior
phase's world-truth facts already use (a Location's canonical name, a
BoundaryRoute's existence, a cross-Region historical relationship, ...).

The one real gap this closes (confirmed by audit): Subregion, Settlement
(as a settlement concept), District, POI, and RegionalBoundary had ZERO
Knowledge integration before this — app.ai.context_builder's own
_regional_context_lines docstring said as much ("never the subregion's
proper name, which has no Knowledge-gating mechanism of its own yet").
Everything here works for those the same way it already works for
Location/NPC/connection facts.

Design:

- A geographic entity is identified the same way every existing subject
  already is: f"{subject_kind}:{entity_id}" (subject_kind is a plain
  string — "location", "region", "subregion", "boundary",
  "boundary_route", ... — matching the established ad hoc convention,
  not a new closed enum; nothing forces every geographic concept through
  one rigid vocabulary).
- What a character knows about that entity is never one boolean. Each
  GeographicKnowledgeAspect (EXISTENCE, NAME, DIRECTION, DISTANCE,
  ROUTE, DESCRIPTION, DANGERS, SERVICES, RELATIONSHIPS) becomes its own
  KnowledgeFact, sharing the entity's subject but keyed by its own
  fact_key: f"{subject_kind}:{entity_id}:{aspect}". Sharing the subject
  (never the aspect) matters concretely: app.ai.context_builder's
  _scene_subjects/relevant_known_facts already match by subject alone,
  so every aspect fact about "the current location" surfaces together
  in narrator context with zero changes to context_builder.

- ensure_geographic_fact establishes WORLD TRUTH — idempotent, grants
  nobody anything (mirrors app.game.world.region_discovery's
  _ensure_rumor_fact pattern from Phase 16U).
- grant_geographic_knowledge is a thin teach_fact wrapper — deliberately
  does NOT auto-create the fact; a caller must ensure_geographic_fact
  first. World truth and "who knows it" stay two explicit steps, exactly
  like every existing example in this codebase (never implicit).
- known_geographic_aspects/knows_geographic_aspect are the read side,
  scoped to one exact knower (PLAYER/NPC/SIMULATED_PLAYER) — an NPC
  knowing a place intimately says nothing about whether the protagonist,
  or any other NPC, knows anything about it at all.

Deliberately NOT built here (later subphases): precision bands
VAGUE/APPROXIMATE/GOOD/PRECISE (17B), rumor-specific plausibility/
contradiction modeling (17C — RUMOR/BELIEVED/CONFIRMED already gives a
reliability axis to build on), any bulk backfill that grants Subregion/
Settlement/POI facts for existing campaigns, and any change to
Location.discovery_status (confirmed dead: zero production reads gate
anything on it) or Region.discovery_status (confirmed a genuine
world-level, non-per-character display value — a narrower, different
concept from what this module tracks, left untouched) or
CharacterLocationDiscovery/CharacterConnectionDiscovery (both represent
physical presence/travel-gating, a different concept from
"informational knowledge about a place", also left untouched).
"""

from sqlalchemy.orm import Session

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType, KnowledgeCertainty
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.game.npcs.service import knows, teach_fact

_PRECISION_RANK = {
    GeographicPrecision.VAGUE: 1,
    GeographicPrecision.APPROXIMATE: 2,
    GeographicPrecision.GOOD: 3,
    GeographicPrecision.PRECISE: 4,
}


def precision_rank(precision: GeographicPrecision) -> int:
    return _PRECISION_RANK[precision]


def geographic_subject(subject_kind: str, entity_id: str) -> str:
    return f"{subject_kind}:{entity_id}"


def geographic_fact_key(subject_kind: str, entity_id: str, aspect: GeographicKnowledgeAspect) -> str:
    return f"{subject_kind}:{entity_id}:{aspect.value.lower()}"


def ensure_geographic_fact(
    db: Session,
    campaign_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
    statement: str,
    *,
    is_secret: bool = False,
    social_priority: int = 1,
) -> KnowledgeFact:
    """World truth only — idempotent, grants nobody anything."""
    fact_key = geographic_fact_key(subject_kind, entity_id, aspect)
    fact = db.query(KnowledgeFact).filter(KnowledgeFact.campaign_id == campaign_id, KnowledgeFact.fact_key == fact_key).first()
    if fact is not None:
        return fact

    fact = KnowledgeFact(
        campaign_id=campaign_id,
        subject=geographic_subject(subject_kind, entity_id),
        fact_key=fact_key,
        statement=statement,
        is_secret=is_secret,
        social_priority=social_priority,
    )
    db.add(fact)
    db.flush()
    return fact


def grant_geographic_knowledge(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
    *,
    source: str = "system",
    certainty: KnowledgeCertainty = KnowledgeCertainty.CONFIRMED,
    precision: GeographicPrecision = GeographicPrecision.VAGUE,
) -> None:
    """Raises ValueError (via teach_fact) if the aspect fact was never
    established with ensure_geographic_fact — world truth must exist
    before anyone can be taught it.

    precision defaults to VAGUE — first knowledge of anything is vague
    (spec's own Arven example: "somewhere south" long before "two weeks
    down the main road"). teach_fact itself knows nothing about
    precision (it's a geography-only concept, not a general Knowledge
    one); this wrapper upgrades KnowledgeKnower.precision afterward,
    monotonically, the same discipline teach_fact already applies to
    certainty — a less-detailed regrant never erases a more-detailed
    one already held."""
    fact_key = geographic_fact_key(subject_kind, entity_id, aspect)
    teach_fact(db, campaign_id, fact_key, knower_type, knower_id, source=source, certainty=certainty)

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
    current_precision = GeographicPrecision(knower.precision) if knower.precision else None
    if current_precision is None or precision_rank(precision) > precision_rank(current_precision):
        knower.precision = precision.value
        db.flush()


def geographic_knowledge_precision(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
) -> GeographicPrecision | None:
    """None means the knower doesn't know this aspect at all (absence =
    ignorance, same convention as everywhere else in Knowledge)."""
    fact_key = geographic_fact_key(subject_kind, entity_id, aspect)
    row = (
        db.query(KnowledgeKnower.precision)
        .join(KnowledgeFact, KnowledgeFact.id == KnowledgeKnower.fact_id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.fact_key == fact_key,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .first()
    )
    if row is None or row[0] is None:
        return None
    return GeographicPrecision(row[0])


def knows_geographic_aspect(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
) -> bool:
    fact_key = geographic_fact_key(subject_kind, entity_id, aspect)
    return knows(db, knower_type, knower_id, fact_key, campaign_id)


def known_geographic_aspects(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subject_kind: str,
    entity_id: str,
) -> set[GeographicKnowledgeAspect]:
    """Which aspects of this exact entity this exact knower currently
    has an explicit KnowledgeKnower row for."""
    subject = geographic_subject(subject_kind, entity_id)
    rows = (
        db.query(KnowledgeFact.fact_key)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.subject == subject,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .all()
    )
    prefix = f"{subject}:"
    aspects: set[GeographicKnowledgeAspect] = set()
    for (fact_key,) in rows:
        if not fact_key.startswith(prefix):
            continue
        raw_aspect = fact_key[len(prefix):]
        try:
            aspects.add(GeographicKnowledgeAspect(raw_aspect.upper()))
        except ValueError:
            continue
    return aspects
