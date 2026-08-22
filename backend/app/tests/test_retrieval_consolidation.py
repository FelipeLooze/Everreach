"""Phase 18E — Character & NPC Long-Term Memory (consolidation)."""

from app.ai.memory_manager import create_memory
from app.ai.retrieval.consolidation import CONSOLIDATION_MEMORY_THRESHOLD, consolidate_memories
from app.core.enums import EventType, KnowledgeDocumentType, KnowledgeSourceType, MemoryOwnerType
from app.ai.retrieval.documents import documents_for_source
from app.game.world.seed import create_campaign
from app.services.event_log import log_event


def _add_memories(db_session, campaign_id, owner_type, owner_id, subject, count, importance=2):
    for index in range(count):
        event = log_event(db_session, campaign_id, EventType.QUEST_STARTED, actor_id=f"actor_{index}")
        create_memory(
            db_session, campaign_id, owner_type, owner_id, subject,
            f"Episódio número {index}.", importance=importance, source_event=event,
        )


def test_below_threshold_produces_no_consolidated_document(db_session):
    campaign = create_campaign(db_session, "Poucas Memorias")
    _add_memories(
        db_session, campaign.id, MemoryOwnerType.NPC, "npc_fake", "character:char_fake",
        CONSOLIDATION_MEMORY_THRESHOLD - 1,
    )

    assert consolidate_memories(
        db_session, campaign.id, MemoryOwnerType.NPC, "npc_fake", "character:char_fake"
    ) is None


def test_reaching_threshold_produces_a_durable_summary_document(db_session):
    campaign = create_campaign(db_session, "Muitas Memorias")
    _add_memories(
        db_session, campaign.id, MemoryOwnerType.NPC, "npc_fake", "character:char_fake",
        CONSOLIDATION_MEMORY_THRESHOLD, importance=3,
    )

    document = consolidate_memories(
        db_session, campaign.id, MemoryOwnerType.NPC, "npc_fake", "character:char_fake"
    )

    assert document is not None
    assert document.document_type == KnowledgeDocumentType.IMPORTANT_HISTORY.value
    assert document.source_id == "npc_fake:character:char_fake"
    assert "Episódio número 0" in document.text
    assert f"Episódio número {CONSOLIDATION_MEMORY_THRESHOLD - 1}" in document.text
    assert "Importância média: 3.0" in document.text
    assert documents_for_source(
        db_session, campaign.id, KnowledgeSourceType.NPC, "npc_fake:character:char_fake"
    ) == [document]


def test_consolidation_never_deletes_the_underlying_memory_rows(db_session):
    from app.db.models.memory import Memory

    campaign = create_campaign(db_session, "Memorias Preservadas")
    _add_memories(
        db_session, campaign.id, MemoryOwnerType.PLAYER, "char_fake", "npc:npc_fake",
        CONSOLIDATION_MEMORY_THRESHOLD,
    )

    consolidate_memories(db_session, campaign.id, MemoryOwnerType.PLAYER, "char_fake", "npc:npc_fake")

    assert (
        db_session.query(Memory)
        .filter(Memory.owner_id == "char_fake", Memory.subject == "npc:npc_fake")
        .count()
        == CONSOLIDATION_MEMORY_THRESHOLD
    )


def test_world_owned_memories_are_never_consolidated(db_session):
    campaign = create_campaign(db_session, "Memoria De Mundo")
    _add_memories(
        db_session, campaign.id, MemoryOwnerType.WORLD, campaign.id, "world",
        CONSOLIDATION_MEMORY_THRESHOLD,
    )

    assert consolidate_memories(
        db_session, campaign.id, MemoryOwnerType.WORLD, campaign.id, "world"
    ) is None


def test_consolidation_maps_player_owner_to_character_source_type(db_session):
    campaign = create_campaign(db_session, "Jogador Consolidado")
    _add_memories(
        db_session, campaign.id, MemoryOwnerType.PLAYER, "char_fake", "location:loc_fake",
        CONSOLIDATION_MEMORY_THRESHOLD,
    )

    document = consolidate_memories(
        db_session, campaign.id, MemoryOwnerType.PLAYER, "char_fake", "location:loc_fake"
    )

    assert document is not None
    assert document.source_type == KnowledgeSourceType.CHARACTER.value
