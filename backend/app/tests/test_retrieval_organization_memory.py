"""Phase 18F — Organization Long-Term Memory."""

from app.ai.retrieval.documents import documents_for_source
from app.ai.retrieval.organizations import (
    index_organization_action,
    institutional_memory_for_member,
    is_active_organization_member,
)
from app.core.enums import (
    CombatActorType,
    KnowledgeDocumentType,
    KnowledgeSourceType,
    OrganizationOrigin,
    OrganizationType,
)
from app.game.organizations.actions import record_organization_action
from app.game.organizations.roles import join_organization
from app.game.world.seed import create_campaign
from app.core.enums import OrganizationActionType
from app.game.organizations.service import create_organization


def _create_org(db_session, campaign_id, name="Guilda"):
    return create_organization(
        db_session, campaign_id, name,
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )


def test_organization_action_becomes_an_institutional_history_document(db_session):
    campaign = create_campaign(db_session, "Memoria Institucional")
    organization = _create_org(db_session, campaign.id)

    action = record_organization_action(
        db_session, organization, OrganizationActionType.OTHER,
        "A guilda firmou um acordo comercial com Cardal.",
    )
    document = index_organization_action(db_session, action)

    assert document is not None
    assert document.document_type == KnowledgeDocumentType.IMPORTANT_HISTORY.value
    assert document.source_id == f"{organization.id}:{action.id}"
    assert "acordo comercial" in document.text
    assert document.occurred_world_minute == action.world_minute


def test_institutional_memory_is_hidden_from_non_members(db_session):
    campaign = create_campaign(db_session, "Memoria Restrita")
    organization = _create_org(db_session, campaign.id)
    action = record_organization_action(
        db_session, organization, OrganizationActionType.OTHER, "Assunto interno da guilda.",
    )
    index_organization_action(db_session, action)

    assert not is_active_organization_member(
        db_session, organization.id, CombatActorType.CHARACTER, "char_outsider"
    )
    assert institutional_memory_for_member(
        db_session, campaign.id, organization.id, CombatActorType.CHARACTER, "char_outsider"
    ) == []


def test_institutional_memory_is_visible_to_active_members(db_session):
    campaign = create_campaign(db_session, "Memoria Visivel")
    organization = _create_org(db_session, campaign.id)
    join_organization(db_session, organization, CombatActorType.CHARACTER, "char_member")
    action = record_organization_action(
        db_session, organization, OrganizationActionType.OTHER, "Assunto interno visível a membros.",
    )
    index_organization_action(db_session, action)

    assert is_active_organization_member(
        db_session, organization.id, CombatActorType.CHARACTER, "char_member"
    )
    documents = institutional_memory_for_member(
        db_session, campaign.id, organization.id, CombatActorType.CHARACTER, "char_member"
    )
    assert len(documents) == 1
    assert "visível a membros" in documents[0].text


def test_institutional_memory_does_not_leak_another_organizations_actions(db_session):
    campaign = create_campaign(db_session, "Memoria Isolada Por Organizacao")
    org_a = _create_org(db_session, campaign.id, "Guilda A")
    org_b = _create_org(db_session, campaign.id, "Guilda B")
    join_organization(db_session, org_a, CombatActorType.CHARACTER, "char_member")
    join_organization(db_session, org_b, CombatActorType.CHARACTER, "char_member")

    action_a = record_organization_action(db_session, org_a, OrganizationActionType.OTHER, "Segredo da Guilda A.")
    action_b = record_organization_action(db_session, org_b, OrganizationActionType.OTHER, "Segredo da Guilda B.")
    index_organization_action(db_session, action_a)
    index_organization_action(db_session, action_b)

    documents_a = institutional_memory_for_member(
        db_session, campaign.id, org_a.id, CombatActorType.CHARACTER, "char_member"
    )
    assert len(documents_a) == 1
    assert "Guilda A" in documents_a[0].text
