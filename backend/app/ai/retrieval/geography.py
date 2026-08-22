"""Phase 18G — Geographic / Regional Knowledge Retrieval.

A geographic canon document existing in the index (Phase 18B) never
implies any given knower may see it — Phase 17's granular per-aspect
geographic Knowledge (KnowledgeFact/KnowledgeKnower under subject
"{kind}:{id}") is the hard gate this module applies before a candidate
document is returned. This is the geography-specific hard filter; scene
proximity/recency/relationship soft-ranking on top of an already-allowed
set is Phase 18K's job, not this one — "do not retrieve distant
geography only because textual similarity is high" is enforced here by
never returning a document the knower has zero Knowledge about in the
first place, regardless of how relevant it might otherwise look.
"""
from sqlalchemy.orm import Session

from app.ai.retrieval.documents import current_documents
from app.core.enums import KnowerType, KnowledgeSourceType
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.knowledge_index import IndexedKnowledgeDocument

GEOGRAPHIC_SOURCE_TYPES = (
    KnowledgeSourceType.REGION,
    KnowledgeSourceType.SUBREGION,
    KnowledgeSourceType.SETTLEMENT,
    KnowledgeSourceType.LOCATION,
)

SOURCE_TYPE_TO_SUBJECT_KIND = {
    KnowledgeSourceType.REGION: "region",
    KnowledgeSourceType.SUBREGION: "subregion",
    KnowledgeSourceType.SETTLEMENT: "settlement",
    KnowledgeSourceType.LOCATION: "location",
}


def knows_about_geographic_subject(
    db: Session, campaign_id: str, knower_type: KnowerType, knower_id: str, subject: str
) -> bool:
    """At least one KnowledgeFact under this subject has been granted to
    this knower — any aspect (Phase 17A's EXISTENCE/NAME/DIRECTION/...)
    is enough to admit the document as a candidate; which specific
    aspects are known is a finer-grained concern for the LLM-facing
    fact list (app.game.npcs.service.relevant_known_facts), not this
    document-level gate."""
    return (
        db.query(KnowledgeFact)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.subject == subject,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .first()
        is not None
    )


def geographic_documents_known_to(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    *,
    source_types: tuple[KnowledgeSourceType, ...] = GEOGRAPHIC_SOURCE_TYPES,
) -> list[IndexedKnowledgeDocument]:
    candidates = current_documents(db, campaign_id, source_types=list(source_types))
    allowed = []
    for document in candidates:
        source_type = KnowledgeSourceType(document.source_type)
        kind = SOURCE_TYPE_TO_SUBJECT_KIND.get(source_type)
        if kind is None:
            continue
        subject = f"{kind}:{document.source_id}"
        if knows_about_geographic_subject(db, campaign_id, knower_type, knower_id, subject):
            allowed.append(document)
    return allowed
