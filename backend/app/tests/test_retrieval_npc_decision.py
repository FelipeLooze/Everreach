"""Phase 18P — NPC Decision Retrieval."""

from app.ai.retrieval.entities import index_npc
from app.ai.retrieval.npc_decision import build_npc_decision_context
from app.ai.retrieval.organizations import index_organization_action
from app.core.enums import (
    CombatActorType,
    GeographicKnowledgeAspect,
    KnowerType,
    OrganizationActionType,
    OrganizationOrigin,
    OrganizationType,
)
from app.db.models.npc import NPC
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.organizations.actions import record_organization_action
from app.game.organizations.roles import join_organization
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def test_npc_decision_context_includes_only_the_npcs_own_knowledge(db_session):
    campaign = create_campaign(db_session, "Decisao De NPC Basica", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro", personality="Rabugento.",
    )
    db_session.add(npc)
    db_session.flush()
    index_npc(db_session, npc)

    context = build_npc_decision_context(db_session, campaign.id, npc)

    assert "Osgar" in context


def test_npc_decision_context_includes_known_geography(db_session):
    campaign = create_campaign(db_session, "Decisao De NPC Geografia", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro",
    )
    db_session.add(npc)
    db_session.flush()

    from app.ai.retrieval.canon import index_region

    index_region(db_session, region)
    ensure_geographic_fact(
        db_session, campaign.id, "region", region.id,
        GeographicKnowledgeAspect.EXISTENCE, "Existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.NPC, npc.id,
        "region", region.id, GeographicKnowledgeAspect.EXISTENCE,
    )

    context = build_npc_decision_context(db_session, campaign.id, npc)

    assert region.name in context


def test_npc_decision_context_includes_institutional_knowledge_for_a_member(db_session):
    campaign = create_campaign(db_session, "Decisao De NPC Organizacao", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro",
    )
    db_session.add(npc)
    db_session.flush()
    organization = create_organization(
        db_session, campaign.id, "Guilda dos Ferreiros",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    join_organization(db_session, organization, CombatActorType.NPC, npc.id)
    action = record_organization_action(
        db_session, organization, OrganizationActionType.OTHER,
        "Registro interno visível a membros da guilda.",
    )
    index_organization_action(db_session, action)

    context = build_npc_decision_context(db_session, campaign.id, npc)

    assert "Registro interno visível a membros" in context


def test_npc_decision_context_never_leaks_unknown_geography(db_session):
    campaign = create_campaign(db_session, "Decisao De NPC Sem Vazamento", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro",
    )
    db_session.add(npc)
    db_session.flush()

    from app.ai.retrieval.canon import index_region

    index_region(db_session, region)
    # Nenhum grant de Knowledge concedido a Osgar sobre a região.

    context = build_npc_decision_context(db_session, campaign.id, npc)

    assert region.name not in context
