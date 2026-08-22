"""Phase 18S — Retrieval Validation & Observability."""

import logging

from app.ai.retrieval.canon import index_region
from app.ai.retrieval.ranking import rank_documents
from app.ai.retrieval.semantic import ScoredDocument
from app.core.enums import GeographicKnowledgeAspect, KnowerType
from app.core.logging import get_logger
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.world.seed import create_campaign, seed_initial_region


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())


def _capture_debug_logs():
    logger = get_logger("context")
    handler = _ListHandler()
    state = (logger.level, logger.disabled, logging.Logger.manager.disable)
    logging.disable(logging.NOTSET)
    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger, handler, state


def _restore(logger, handler, state):
    logger.removeHandler(handler)
    logger.setLevel(state[0])
    logger.disabled = state[1]
    logging.disable(state[2])


def test_rank_documents_logs_a_trace_with_accessible_and_filtered_candidates(db_session):
    campaign = create_campaign(db_session, "Trace De Retrieval", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan")
    accessible = index_region(db_session, region)
    ensure_geographic_fact(
        db_session, campaign.id, "region", region.id,
        GeographicKnowledgeAspect.EXISTENCE, "Existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        "region", region.id, GeographicKnowledgeAspect.EXISTENCE,
    )

    logger, handler, state = _capture_debug_logs()
    try:
        rank_documents(
            db_session, campaign.id, [ScoredDocument(accessible, 0.8)],
            KnowerType.PLAYER, character.id,
            query_description="pergunta de teste",
        )
    finally:
        _restore(logger, handler, state)

    messages = "\n".join(handler.records)
    assert "RETRIEVAL TRACE" in messages
    assert "pergunta de teste" in messages
    assert "SELECTED" in messages


def test_rank_documents_trace_marks_inaccessible_candidates_as_filtered(db_session):
    campaign = create_campaign(db_session, "Trace Filtrado", world_seed=2)
    region, _village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan")
    inaccessible = index_region(db_session, region)
    # Nenhum grant de Knowledge concedido — o personagem não conhece a região.

    logger, handler, state = _capture_debug_logs()
    try:
        rank_documents(
            db_session, campaign.id, [ScoredDocument(inaccessible, 0.9)],
            KnowerType.PLAYER, character.id,
        )
    finally:
        _restore(logger, handler, state)

    messages = "\n".join(handler.records)
    assert "FILTERED (not accessible to this knower)" in messages
    assert "SELECTED" not in messages


def test_rank_documents_trace_is_silent_above_debug_level(db_session):
    campaign = create_campaign(db_session, "Sem Trace Acima De Debug", world_seed=3)
    region, _village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan")
    document = index_region(db_session, region)

    logger = get_logger("context")
    handler = _ListHandler()
    state = (logger.level, logger.disabled, logging.Logger.manager.disable)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        rank_documents(
            db_session, campaign.id, [ScoredDocument(document, 0.5)],
            KnowerType.PLAYER, character.id,
        )
    finally:
        _restore(logger, handler, state)

    assert handler.records == []
