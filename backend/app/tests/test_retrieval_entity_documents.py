"""Phase 18D — Entity Knowledge Documents (NPC chunking)."""

from app.ai.retrieval.documents import documents_for_source
from app.ai.retrieval.entities import index_npc, index_npc_relationship
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.db.models.npc import NPC
from app.db.models.relationship import CharacterNPCRelationship
from app.game.character.service import create_character
from app.game.world.seed import create_campaign, seed_initial_region


def test_index_npc_creates_separate_identity_and_background_chunks(db_session):
    campaign = create_campaign(db_session, "NPC Fragmentado", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro", personality="Rabugento mas leal.",
        backstory="Aprendeu o ofício com o pai antes da guerra.",
    )
    db_session.add(npc)
    db_session.flush()

    documents = index_npc(db_session, npc)

    assert len(documents) == 2
    by_type = {doc.document_type: doc for doc in documents}
    assert "Osgar" in by_type[KnowledgeDocumentType.IDENTITY.value].text
    assert "ferreiro" in by_type[KnowledgeDocumentType.IDENTITY.value].text
    assert "guerra" in by_type[KnowledgeDocumentType.BACKGROUND.value].text
    # Nunca um documento monolítico misturando identidade e história.
    assert "guerra" not in by_type[KnowledgeDocumentType.IDENTITY.value].text


def test_index_npc_without_backstory_creates_only_identity(db_session):
    campaign = create_campaign(db_session, "NPC Sem Historia", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Mira", role="taverneira",
    )
    db_session.add(npc)
    db_session.flush()

    documents = index_npc(db_session, npc)

    assert len(documents) == 1
    assert documents[0].document_type == KnowledgeDocumentType.IDENTITY.value


def test_index_npc_relationship_is_keyed_by_the_npc_character_pair(db_session):
    campaign = create_campaign(db_session, "Relacao Indexada", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro",
    )
    db_session.add(npc)
    db_session.flush()
    db_session.add(
        CharacterNPCRelationship(
            campaign_id=campaign.id, character_id=character.id, npc_id=npc.id,
            familiarity=40, trust=10, affinity=5,
        )
    )
    db_session.flush()

    document = index_npc_relationship(db_session, npc, character)

    assert document is not None
    assert document.source_id == f"{npc.id}:{character.id}"
    assert "Logan" in document.text and "Osgar" in document.text
    assert "confiança 10" in document.text
    # O documento de relação usa uma chave composta — não colide com a
    # chave de identidade do NPC, que é só o próprio npc.id.
    assert documents_for_source(db_session, campaign.id, KnowledgeSourceType.NPC, npc.id) == []
    index_npc(db_session, npc)
    identity_docs = documents_for_source(db_session, campaign.id, KnowledgeSourceType.NPC, npc.id)
    assert len(identity_docs) == 1
    assert identity_docs[0].document_type == KnowledgeDocumentType.IDENTITY.value


def test_index_npc_relationship_returns_none_when_no_relationship_recorded(db_session):
    campaign = create_campaign(db_session, "Sem Relacao", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro",
    )
    db_session.add(npc)
    db_session.flush()

    assert index_npc_relationship(db_session, npc, character) is None
