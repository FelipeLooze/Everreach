"""Phase 18L — Context Budget & Compression."""

from app.ai.retrieval.budget import fit_to_budget, format_ranked_documents
from app.ai.retrieval.ranking import RankedDocument
from app.core.enums import KnowledgeDocumentType
from app.db.models.knowledge_index import IndexedKnowledgeDocument


def _doc(document_id: str, text: str, document_type: KnowledgeDocumentType) -> IndexedKnowledgeDocument:
    return IndexedKnowledgeDocument(
        id=document_id, campaign_id="campaign_fake", source_type="NPC",
        source_id="npc_fake", document_type=document_type.value, text=text,
    )


def _ranked(document: IndexedKnowledgeDocument, score: float) -> RankedDocument:
    return RankedDocument(
        document=document, score=score, semantic_score=score,
        entity_match=False, recency_score=0.5, importance_score=0.5,
    )


def test_fit_to_budget_includes_highest_ranked_first():
    first = _ranked(_doc("idoc_1", "a" * 100, KnowledgeDocumentType.IDENTITY), 0.9)
    second = _ranked(_doc("idoc_2", "b" * 100, KnowledgeDocumentType.BACKGROUND), 0.5)

    result = fit_to_budget([first, second], max_chars=1000)

    assert [ranked.document.id for ranked in result.included] == ["idoc_1", "idoc_2"]
    assert result.used_chars == 200
    assert result.dropped_count == 0


def test_fit_to_budget_drops_only_the_lowest_ranked_remainder():
    """Never a best-fit shuffle: once a higher-ranked item doesn't fit,
    nothing lower-ranked is allowed to sneak in ahead of it either, even
    if it would technically fit in the remaining space."""
    first = _ranked(_doc("idoc_1", "a" * 80, KnowledgeDocumentType.IDENTITY), 0.9)
    too_big = _ranked(_doc("idoc_2", "b" * 50, KnowledgeDocumentType.BACKGROUND), 0.6)
    small_enough = _ranked(_doc("idoc_3", "c" * 5, KnowledgeDocumentType.IMPORTANT_HISTORY), 0.3)

    result = fit_to_budget([first, too_big, small_enough], max_chars=100)

    assert [ranked.document.id for ranked in result.included] == ["idoc_1"]
    assert result.dropped_count == 2


def test_fit_to_budget_deduplicates_by_document_id():
    document = _doc("idoc_1", "a" * 50, KnowledgeDocumentType.IDENTITY)
    first = _ranked(document, 0.9)
    duplicate = _ranked(document, 0.9)

    result = fit_to_budget([first, duplicate], max_chars=1000)

    assert len(result.included) == 1
    assert result.used_chars == 50


def test_format_ranked_documents_produces_labeled_sections_not_a_blob():
    identity = _ranked(_doc("idoc_1", "Osgar é ferreiro.", KnowledgeDocumentType.IDENTITY), 0.9)
    history = _ranked(_doc("idoc_2", "A ponte caiu.", KnowledgeDocumentType.HISTORICAL_EVENT), 0.5)

    formatted = format_ranked_documents([identity, history])

    assert "RELEVANT IDENTITY" in formatted
    assert "RELEVANT WORLD HISTORY" in formatted
    assert "- Osgar é ferreiro." in formatted
    assert "- A ponte caiu." in formatted


def test_format_ranked_documents_groups_same_type_documents_together():
    first = _ranked(_doc("idoc_1", "Primeiro fato.", KnowledgeDocumentType.BACKGROUND), 0.9)
    second = _ranked(_doc("idoc_2", "Segundo fato.", KnowledgeDocumentType.BACKGROUND), 0.5)

    formatted = format_ranked_documents([first, second])

    assert formatted.count("RELEVANT BACKGROUND") == 1
    assert "- Primeiro fato." in formatted
    assert "- Segundo fato." in formatted
