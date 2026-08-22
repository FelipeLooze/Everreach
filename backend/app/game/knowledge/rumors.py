"""Phase 17C — Rumors & Geographic Information Sources.

Rumors are NOT world truth (spec). A rumor's statement may not match
Canon at all — the "Ancient Tunnel" example: Canon says the entrance
collapsed 20 years ago; the rumor a traveler repeats says merchants
still use it. Both can exist as real, independent KnowledgeFact rows
about the same subject; nothing here ever overwrites the canonical
aspect fact app.game.knowledge.geography.ensure_geographic_fact
establishes elsewhere.

A rumor is keyed by its own rumor_key (caller-chosen — typically the
NPC/source id, or any stable label distinguishing this rumor from
others), so distinct rumor_keys about the same (entity, aspect) can
coexist without collision — the actual reconciliation of possibly
contradictory rumors is 17N's job, not this one; 17C only needs
multiple independent rumor facts to be representable at all, which a
unique fact_key per rumor_key already gives for free.

Reuses app.game.knowledge.geography's grant primitive (precision
upgrade included) rather than reimplementing it — a rumor is granted
exactly like any other geographic fact, just under a fact_key in the
":rumor:" namespace and, by convention (never enforced structurally,
since the underlying KnowledgeKnower row is identical either way),
usually at RUMOR or BELIEVED certainty.
"""

from sqlalchemy.orm import Session

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType, KnowledgeCertainty, RumorAccuracy
from app.db.models.knowledge import KnowledgeFact
from app.game.knowledge.geography import geographic_fact_key, geographic_subject, grant_fact_with_precision
from app.game.npcs.service import knows


def rumor_fact_key(subject_kind: str, entity_id: str, aspect: GeographicKnowledgeAspect, rumor_key: str) -> str:
    return f"{geographic_fact_key(subject_kind, entity_id, aspect)}:rumor:{rumor_key}"


def establish_rumor(
    db: Session,
    campaign_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
    rumor_key: str,
    statement: str,
    accuracy: RumorAccuracy,
    *,
    is_secret: bool = False,
    social_priority: int = 1,
) -> KnowledgeFact:
    """World truth about the RUMOR itself (that this rumor circulates,
    and the backend's own private read on its accuracy) — idempotent,
    grants nobody anything. Does not touch, and is never touched by, the
    canonical aspect fact for the same (entity, aspect)."""
    fact_key = rumor_fact_key(subject_kind, entity_id, aspect, rumor_key)
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
        rumor_accuracy=accuracy.value,
    )
    db.add(fact)
    db.flush()
    return fact


def grant_rumor(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
    rumor_key: str,
    *,
    source: str,
    certainty: KnowledgeCertainty = KnowledgeCertainty.RUMOR,
    precision: GeographicPrecision = GeographicPrecision.VAGUE,
) -> None:
    """Raises ValueError (via teach_fact) if establish_rumor was never
    called for this rumor_key. source is required (never "system") —
    a rumor always comes from somewhere (a traveler, a book, an old
    map), unlike some world-truth grants which are legitimately
    system-sourced."""
    fact_key = rumor_fact_key(subject_kind, entity_id, aspect, rumor_key)
    grant_fact_with_precision(
        db, campaign_id, fact_key, knower_type, knower_id,
        source=source, certainty=certainty, precision=precision,
    )


def knows_rumor(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
    rumor_key: str,
) -> bool:
    fact_key = rumor_fact_key(subject_kind, entity_id, aspect, rumor_key)
    return knows(db, knower_type, knower_id, fact_key, campaign_id)
