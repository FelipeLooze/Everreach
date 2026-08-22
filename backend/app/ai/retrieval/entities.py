"""Phase 18D — Entity Knowledge Documents.

Deliberately small, targeted chunks per NPC instead of one monolithic
per-NPC document (spec's own OSGAR_FULL_CONTEXT.txt counter-example):
IDENTITY and BACKGROUND describe the NPC alone; RELATIONSHIP describes
one specific NPC-character pair and is therefore keyed by a compound
source_id ("{npc_id}:{character_id}") rather than the NPC id alone —
Everreach has exactly one protagonist per campaign today, but a
relationship document is honestly about the PAIR, not the NPC in
isolation, so the storage key says so rather than assuming there is
only ever one relationship to find.
"""
from sqlalchemy.orm import Session

from app.ai.retrieval.documents import upsert_document
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.db.models.character import Character
from app.db.models.knowledge_index import IndexedKnowledgeDocument
from app.db.models.npc import NPC
from app.game.relationships.service import get_character_npc_relationship


def index_npc(db: Session, npc: NPC) -> list[IndexedKnowledgeDocument]:
    documents = [
        upsert_document(
            db,
            npc.campaign_id,
            KnowledgeSourceType.NPC,
            npc.id,
            KnowledgeDocumentType.IDENTITY,
            f"{npc.name}, {npc.role}. {npc.personality}".strip(),
        )
    ]
    if npc.backstory:
        documents.append(
            upsert_document(
                db,
                npc.campaign_id,
                KnowledgeSourceType.NPC,
                npc.id,
                KnowledgeDocumentType.BACKGROUND,
                f"{npc.name}: {npc.backstory}",
            )
        )
    return documents


def index_npc_relationship(
    db: Session, npc: NPC, character: Character
) -> IndexedKnowledgeDocument | None:
    relationship = get_character_npc_relationship(db, npc.campaign_id, character.id, npc.id)
    if relationship is None:
        return None
    text = (
        f"Relação entre {character.name} e {npc.name}: "
        f"familiaridade {relationship.familiarity}, confiança {relationship.trust}, "
        f"afinidade {relationship.affinity}."
    )
    return upsert_document(
        db,
        npc.campaign_id,
        KnowledgeSourceType.NPC,
        f"{npc.id}:{character.id}",
        KnowledgeDocumentType.RELATIONSHIP,
        text,
        source_version=f"{relationship.familiarity}:{relationship.trust}:{relationship.affinity}",
    )
