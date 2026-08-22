"""Phase 18I — Knowledge-Aware Retrieval."""

from app.ai.retrieval.access import is_document_accessible_to, knowledge_aware_documents
from app.ai.retrieval.canon import index_organization, index_region
from app.ai.retrieval.consolidation import consolidate_memories
from app.ai.retrieval.entities import index_npc, index_npc_relationship
from app.ai.retrieval.history import index_historical_event
from app.ai.retrieval.organizations import index_organization_action
from app.core.enums import (
    CombatActorType,
    EventType,
    GeographicKnowledgeAspect,
    KnowerType,
    KnowledgeDocumentType,
    KnowledgeSourceType,
    MemoryOwnerType,
    OrganizationActionType,
    OrganizationOrigin,
    OrganizationType,
    OrganizationVisibility,
)
from app.ai.memory_manager import create_memory
from app.ai.retrieval.consolidation import CONSOLIDATION_MEMORY_THRESHOLD
from app.db.models.npc import NPC
from app.db.models.relationship import CharacterNPCRelationship
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.organizations.actions import record_organization_action
from app.game.organizations.roles import join_organization
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region
from app.services.event_log import log_event


def test_geographic_documents_reuse_the_geography_gate(db_session):
    campaign = create_campaign(db_session, "Acesso Geografico", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan")
    document = index_region(db_session, region)

    assert not is_document_accessible_to(
        db_session, campaign.id, document, KnowerType.PLAYER, character.id
    )

    ensure_geographic_fact(
        db_session, campaign.id, "region", region.id,
        GeographicKnowledgeAspect.EXISTENCE, "Existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        "region", region.id, GeographicKnowledgeAspect.EXISTENCE,
    )

    assert is_document_accessible_to(
        db_session, campaign.id, document, KnowerType.PLAYER, character.id
    )


def test_public_organization_identity_is_visible_to_everyone(db_session):
    campaign = create_campaign(db_session, "Organizacao Publica")
    organization = create_organization(
        db_session, campaign.id, "Guilda Aberta",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
        visibility=OrganizationVisibility.PUBLIC,
    )
    document = index_organization(db_session, organization)

    assert is_document_accessible_to(
        db_session, campaign.id, document, KnowerType.PLAYER, "char_outsider"
    )


def test_private_organization_identity_requires_membership(db_session):
    campaign = create_campaign(db_session, "Organizacao Privada")
    organization = create_organization(
        db_session, campaign.id, "Sociedade Secreta",
        organization_type=OrganizationType.CRIMINAL, origin=OrganizationOrigin.NATIVE,
        visibility=OrganizationVisibility.PRIVATE,
    )
    document = index_organization(db_session, organization)

    assert not is_document_accessible_to(
        db_session, campaign.id, document, KnowerType.PLAYER, "char_outsider"
    )

    join_organization(db_session, organization, CombatActorType.CHARACTER, "char_member")
    assert is_document_accessible_to(
        db_session, campaign.id, document, KnowerType.PLAYER, "char_member"
    )


def test_institutional_history_requires_membership_even_for_public_organizations(db_session):
    campaign = create_campaign(db_session, "Historico Institucional Publico")
    organization = create_organization(
        db_session, campaign.id, "Guilda Aberta Com Segredos",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
        visibility=OrganizationVisibility.PUBLIC,
    )
    action = record_organization_action(
        db_session, organization, OrganizationActionType.OTHER, "Registro interno.",
    )
    document = index_organization_action(db_session, action)

    assert not is_document_accessible_to(
        db_session, campaign.id, document, KnowerType.PLAYER, "char_outsider"
    )

    join_organization(db_session, organization, CombatActorType.CHARACTER, "char_member")
    assert is_document_accessible_to(
        db_session, campaign.id, document, KnowerType.PLAYER, "char_member"
    )


def test_npc_identity_requires_having_met_the_npc(db_session):
    campaign = create_campaign(db_session, "Conheceu O NPC", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    npc = NPC(campaign_id=campaign.id, region_id=region.id, location_id=village.id, name="Osgar", role="ferreiro")
    db_session.add(npc)
    db_session.flush()
    documents = index_npc(db_session, npc)
    identity = next(doc for doc in documents if doc.document_type == KnowledgeDocumentType.IDENTITY.value)

    assert not is_document_accessible_to(db_session, campaign.id, identity, KnowerType.PLAYER, character.id)

    db_session.add(CharacterNPCRelationship(campaign_id=campaign.id, character_id=character.id, npc_id=npc.id))
    db_session.flush()

    assert is_document_accessible_to(db_session, campaign.id, identity, KnowerType.PLAYER, character.id)
    # O próprio NPC sempre "conhece" a si mesmo.
    assert is_document_accessible_to(db_session, campaign.id, identity, KnowerType.NPC, npc.id)


def test_npc_relationship_document_is_only_visible_to_its_two_participants(db_session):
    campaign = create_campaign(db_session, "Relacao Restrita", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    other_character = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    npc = NPC(campaign_id=campaign.id, region_id=region.id, location_id=village.id, name="Osgar", role="ferreiro")
    db_session.add(npc)
    db_session.flush()
    db_session.add(CharacterNPCRelationship(campaign_id=campaign.id, character_id=character.id, npc_id=npc.id))
    db_session.flush()
    document = index_npc_relationship(db_session, npc, character)

    assert is_document_accessible_to(db_session, campaign.id, document, KnowerType.PLAYER, character.id)
    assert is_document_accessible_to(db_session, campaign.id, document, KnowerType.NPC, npc.id)
    assert not is_document_accessible_to(db_session, campaign.id, document, KnowerType.PLAYER, other_character.id)


def test_consolidated_memory_is_only_visible_to_its_own_owner(db_session):
    campaign = create_campaign(db_session, "Memoria Propria")
    for index in range(CONSOLIDATION_MEMORY_THRESHOLD):
        event = log_event(db_session, campaign.id, EventType.QUEST_STARTED)
        create_memory(
            db_session, campaign.id, MemoryOwnerType.PLAYER, "char_owner", "npc:npc_fake",
            f"Episódio {index}.", importance=2, source_event=event,
        )
    document = consolidate_memories(
        db_session, campaign.id, MemoryOwnerType.PLAYER, "char_owner", "npc:npc_fake"
    )

    assert is_document_accessible_to(db_session, campaign.id, document, KnowerType.PLAYER, "char_owner")
    assert not is_document_accessible_to(db_session, campaign.id, document, KnowerType.PLAYER, "char_other")
    assert not is_document_accessible_to(db_session, campaign.id, document, KnowerType.NPC, "char_owner")


def test_historical_event_documents_have_no_access_story_yet_and_are_denied(db_session):
    campaign = create_campaign(db_session, "Evento Sem Historia De Acesso")
    event = log_event(
        db_session, campaign.id, EventType.PLAYER_LEVELED_UP,
        actor_type="character", actor_id="char_fake", payload={"new_level": 2},
    )
    document = index_historical_event(db_session, event)

    assert not is_document_accessible_to(
        db_session, campaign.id, document, KnowerType.PLAYER, "char_fake"
    )


def test_knowledge_aware_documents_combines_candidates_and_the_filter(db_session):
    campaign = create_campaign(db_session, "Combinado", world_seed=4)
    region, _village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan")
    index_region(db_session, region)
    ensure_geographic_fact(
        db_session, campaign.id, "region", region.id,
        GeographicKnowledgeAspect.EXISTENCE, "Existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        "region", region.id, GeographicKnowledgeAspect.EXISTENCE,
    )

    documents = knowledge_aware_documents(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        source_types=[KnowledgeSourceType.REGION],
    )

    assert documents
    assert all(document.source_id == region.id for document in documents)
