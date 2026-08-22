"""Phase 18H — Semantic Retrieval."""

from app.ai.llm_service import LLMService
from app.ai.retrieval.documents import upsert_document
from app.ai.retrieval.semantic import cosine_similarity, embed_document, semantic_search
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.game.world.seed import create_campaign

_VOCAB = ["montanha", "rio", "vila", "floresta"]


class _FakeEmbeddingLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return ""

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(word)) for word in _VOCAB]


class _NoEmbeddingLLM(LLMService):
    """Only implements generate() — matches the ~45 existing test doubles
    across the suite that never needed embed(); confirms the default
    LLMService.embed() degrades gracefully rather than breaking them."""

    def generate(self, system: str, prompt: str) -> str:
        return ""


def test_cosine_similarity_basic_cases():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_embed_document_stores_embedding_when_supported(db_session):
    campaign = create_campaign(db_session, "Embedding Suportado")
    document = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake",
        KnowledgeDocumentType.IDENTITY, "Uma vila cercada por montanhas.",
    )

    stored = embed_document(db_session, _FakeEmbeddingLLM(), document)

    assert stored is True
    assert document.embedding_json is not None


def test_embed_document_returns_false_when_llm_does_not_support_it(db_session):
    campaign = create_campaign(db_session, "Sem Embedding")
    document = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake",
        KnowledgeDocumentType.IDENTITY, "Texto qualquer.",
    )

    stored = embed_document(db_session, _NoEmbeddingLLM(), document)

    assert stored is False
    assert document.embedding_json is None


def test_semantic_search_ranks_by_similarity_to_query(db_session):
    campaign = create_campaign(db_session, "Busca Semantica")
    llm = _FakeEmbeddingLLM()
    mountain_doc = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_montanha",
        KnowledgeDocumentType.IDENTITY, "Uma cordilheira de montanhas geladas.",
    )
    river_doc = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_rio",
        KnowledgeDocumentType.IDENTITY, "Um rio calmo cortando a planície.",
    )
    embed_document(db_session, llm, mountain_doc)
    embed_document(db_session, llm, river_doc)

    results = semantic_search(db_session, llm, campaign.id, "Onde ficam as montanhas?")

    assert results[0].document.id == mountain_doc.id
    assert results[0].score > results[1].score


def test_semantic_search_excludes_documents_without_a_stored_embedding(db_session):
    campaign = create_campaign(db_session, "Sem Vetor Ainda")
    llm = _FakeEmbeddingLLM()
    embedded = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_a",
        KnowledgeDocumentType.IDENTITY, "Uma vila na floresta.",
    )
    unembedded = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_b",
        KnowledgeDocumentType.IDENTITY, "Uma vila no rio.",
    )
    embed_document(db_session, llm, embedded)

    results = semantic_search(db_session, llm, campaign.id, "vila")

    assert [scored.document.id for scored in results] == [embedded.id]
    assert unembedded.id not in [scored.document.id for scored in results]


def test_semantic_search_returns_nothing_when_embeddings_are_unavailable(db_session):
    campaign = create_campaign(db_session, "Embedding Indisponivel")
    document = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_a",
        KnowledgeDocumentType.IDENTITY, "Texto qualquer.",
    )
    embed_document(db_session, _FakeEmbeddingLLM(), document)

    results = semantic_search(db_session, _NoEmbeddingLLM(), campaign.id, "texto")

    assert results == []


def test_semantic_search_is_campaign_scoped(db_session):
    first = create_campaign(db_session, "Busca Campanha A")
    second = create_campaign(db_session, "Busca Campanha B")
    llm = _FakeEmbeddingLLM()
    doc_a = upsert_document(
        db_session, first.id, KnowledgeSourceType.REGION, "region_a",
        KnowledgeDocumentType.IDENTITY, "Uma vila na montanha.",
    )
    doc_b = upsert_document(
        db_session, second.id, KnowledgeSourceType.REGION, "region_b",
        KnowledgeDocumentType.IDENTITY, "Uma vila na montanha.",
    )
    embed_document(db_session, llm, doc_a)
    embed_document(db_session, llm, doc_b)

    results = semantic_search(db_session, llm, first.id, "montanha")

    assert [scored.document.id for scored in results] == [doc_a.id]
