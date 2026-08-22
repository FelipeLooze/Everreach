"""Phase 18Q — Organization Decision Retrieval."""

from app.ai.retrieval.canon import index_region
from app.ai.retrieval.organization_decision import build_organization_decision_context
from app.ai.retrieval.organizations import index_organization_action
from app.core.enums import (
    GeographicKnowledgeAspect,
    KnowerType,
    OrganizationActionType,
    OrganizationOrigin,
    OrganizationType,
)
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.organizations.actions import record_organization_action
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def test_organization_decision_context_includes_own_institutional_memory_without_membership(db_session):
    """An organization always has full access to its OWN institutional
    records — this is not a membership question the way it is for an
    individual NPC/character consulting them."""
    campaign = create_campaign(db_session, "Decisao De Organizacao Basica")
    organization = create_organization(
        db_session, campaign.id, "Guilda dos Ferreiros",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    action = record_organization_action(
        db_session, organization, OrganizationActionType.OTHER,
        "Contrato firmado com um fornecedor de minério.",
    )
    index_organization_action(db_session, action)

    context = build_organization_decision_context(db_session, campaign.id, organization)

    assert "Contrato firmado com um fornecedor" in context


def test_organization_decision_context_includes_known_geography(db_session):
    campaign = create_campaign(db_session, "Decisao De Organizacao Geografia", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)
    organization = create_organization(
        db_session, campaign.id, "Guilda dos Exploradores",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    index_region(db_session, region)
    ensure_geographic_fact(
        db_session, campaign.id, "region", region.id,
        GeographicKnowledgeAspect.EXISTENCE, "Existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.ORGANIZATION, organization.id,
        "region", region.id, GeographicKnowledgeAspect.EXISTENCE,
    )

    context = build_organization_decision_context(db_session, campaign.id, organization)

    assert region.name in context


def test_organization_decision_context_never_leaks_another_organizations_records(db_session):
    campaign = create_campaign(db_session, "Decisao Isolada Entre Organizacoes")
    organization_a = create_organization(
        db_session, campaign.id, "Guilda A",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    organization_b = create_organization(
        db_session, campaign.id, "Guilda B",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    action = record_organization_action(
        db_session, organization_b, OrganizationActionType.OTHER, "Segredo exclusivo da Guilda B.",
    )
    index_organization_action(db_session, action)

    context = build_organization_decision_context(db_session, campaign.id, organization_a)

    assert "Segredo exclusivo" not in context
