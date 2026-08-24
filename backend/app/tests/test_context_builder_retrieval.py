"""Phase 18N — Context Builder Integration."""

from app.ai.context_builder import build_context
from app.ai.retrieval.documents import supersede_document
from app.ai.retrieval.entities import index_npc_relationship
from app.ai.retrieval.organizations import index_organization_action
from app.core.enums import (
    CombatActorType,
    KnowledgeDocumentType,
    KnowledgeSourceType,
    OrganizationActionType,
    OrganizationOrigin,
    OrganizationType,
)
from app.db.models.npc import NPC
from app.db.models.relationship import CharacterNPCRelationship
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.organizations.actions import record_organization_action
from app.game.organizations.roles import join_organization
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def test_build_context_includes_accessible_long_term_relationship_memory(db_session):
    campaign = create_campaign(db_session, "Contexto Com Relacao", world_seed=1)
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
            familiarity=40, trust=15, affinity=5,
        )
    )
    db_session.flush()
    index_npc_relationship(db_session, npc, character)

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state, active_interlocutor=npc.id)

    assert "RELEVANT RELATIONSHIP CONTEXT" in context
    assert "confiança 15" in context


def test_build_context_never_leaks_institutional_records_the_character_cannot_access(db_session):
    campaign = create_campaign(db_session, "Contexto Sem Vazamento", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    organization = create_organization(
        db_session, campaign.id, "Sociedade Secreta",
        organization_type=OrganizationType.CRIMINAL, origin=OrganizationOrigin.NATIVE,
    )
    action = record_organization_action(
        db_session, organization, OrganizationActionType.OTHER,
        "Segredo institucional que o personagem nunca deveria ver.",
    )
    index_organization_action(db_session, action)

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state)

    assert "Segredo institucional" not in context


def test_build_context_shows_none_recalled_when_nothing_is_retrievable(db_session):
    campaign = create_campaign(db_session, "Contexto Vazio", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state)

    assert "RELEVANT LONG-TERM KNOWLEDGE\n- none recalled" in context


def test_build_context_includes_institutional_memory_for_an_active_member(db_session):
    campaign = create_campaign(db_session, "Contexto Membro Ativo", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    organization = create_organization(
        db_session, campaign.id, "Guilda Dos Ferreiros",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    join_organization(db_session, organization, CombatActorType.CHARACTER, character.id)
    action = record_organization_action(
        db_session, organization, OrganizationActionType.OTHER,
        "Registro visível apenas a membros da guilda.",
    )
    index_organization_action(db_session, action)

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state)

    assert "Registro visível apenas a membros" in context


# --- Phase 24N — RAG / Long-Term Memory Narrative Integration ---


def test_retrieved_long_term_knowledge_carries_the_not_truth_disclaimer(db_session):
    campaign = create_campaign(db_session, "Contexto Com Disclaimer", world_seed=5)
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
            familiarity=40, trust=15, affinity=5,
        )
    )
    db_session.flush()
    index_npc_relationship(db_session, npc, character)

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state, active_interlocutor=npc.id)

    assert "never overrides the current authoritative state" in context


def test_superseded_long_term_document_never_reaches_the_context_only_the_current_version_does(
    db_session,
):
    # The spec's own explicit ask: "old RAG fact conflicts with new
    # current state -> current authoritative state must win." Exercised
    # here directly at the layer context_builder actually queries
    # (documents_current, via knowledge_aware_documents), using the real
    # supersede_document mechanism (Phase 18M) rather than just the
    # lower-level primitives already covered in test_retrieval_temporal.py
    # or the downstream narration validator already covered in
    # test_narrative_temporal.py — this is the missing middle layer:
    # context_builder's own retrieval integration.
    campaign = create_campaign(db_session, "Contexto Substituido", world_seed=6)
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
            familiarity=40, trust=15, affinity=5,
        )
    )
    db_session.flush()
    index_npc_relationship(db_session, npc, character)

    state = build_game_state(db_session, campaign.id, character.id)
    context_before = build_context(db_session, state, active_interlocutor=npc.id)
    assert "confiança 15" in context_before

    # Genuine supersession (not a cosmetic re-derivation): trust improved
    # from a real relationship-changing event.
    supersede_document(
        db_session,
        campaign.id,
        KnowledgeSourceType.NPC,
        f"{npc.id}:{character.id}",
        KnowledgeDocumentType.RELATIONSHIP,
        f"Relação entre {character.name} e {npc.name}: "
        "familiaridade 60, confiança 45, afinidade 20.",
    )

    context_after = build_context(db_session, state, active_interlocutor=npc.id)

    assert "confiança 15" not in context_after
    assert "confiança 45" in context_after
