"""Phase 18M — Index Update / Supersession / Invalidation."""

from app.ai.retrieval.canon import index_organization
from app.ai.retrieval.documents import documents_for_source, supersede_document
from app.ai.retrieval.organizations import reindex_organization_current_state
from app.ai.retrieval.temporal import documents_historical
from app.core.enums import (
    KnowledgeDocumentType,
    KnowledgeSourceType,
    OrganizationOrigin,
    OrganizationStatus,
    OrganizationType,
)
from app.game.organizations.service import create_organization, set_organization_status
from app.game.world.seed import create_campaign


def _create_org(db_session, campaign_id):
    return create_organization(
        db_session, campaign_id, "Guilda dos Mercadores",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
        description="Regula o comércio local.",
    )


def test_supersede_document_is_a_no_op_when_text_is_unchanged(db_session):
    campaign = create_campaign(db_session, "Sem Mudanca")
    first = supersede_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "npc_fake",
        KnowledgeDocumentType.CURRENT_STATE, "Mesmo texto.",
    )

    second = supersede_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "npc_fake",
        KnowledgeDocumentType.CURRENT_STATE, "Mesmo texto.",
    )

    assert first.id == second.id
    assert first.is_current is True
    assert documents_historical(db_session, campaign.id) == []


def test_supersede_document_preserves_the_old_version_as_historical(db_session):
    campaign = create_campaign(db_session, "Com Mudanca")
    original = supersede_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "cardal_blacksmith",
        KnowledgeDocumentType.CURRENT_STATE, "Osgar é o ferreiro de Cardal.",
        occurred_world_minute=100,
    )

    updated = supersede_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "cardal_blacksmith",
        KnowledgeDocumentType.CURRENT_STATE, "Mira é a ferreira de Cardal.",
        occurred_world_minute=500,
    )

    assert updated.id != original.id
    assert updated.text == "Mira é a ferreira de Cardal."

    current = documents_for_source(db_session, campaign.id, KnowledgeSourceType.NPC, "cardal_blacksmith")
    assert current == [updated]

    historical = documents_historical(db_session, campaign.id)
    assert len(historical) == 1
    assert historical[0].id == original.id
    assert historical[0].text == "Osgar é o ferreiro de Cardal."


def test_reindex_organization_current_state_supersedes_only_on_real_change(db_session):
    campaign = create_campaign(db_session, "Reindex Organizacao")
    organization = _create_org(db_session, campaign.id)
    index_organization(db_session, organization)

    unchanged = reindex_organization_current_state(db_session, organization, occurred_world_minute=0)
    assert documents_historical(db_session, campaign.id) == []

    organization.status = OrganizationStatus.DISBANDED
    db_session.flush()
    changed = reindex_organization_current_state(db_session, organization, occurred_world_minute=100)

    assert changed.id != unchanged.id
    assert "DISBANDED" in changed.text
    historical = documents_historical(db_session, campaign.id)
    assert len(historical) == 1
    assert "ACTIVE" in historical[0].text


def test_organization_status_change_automatically_reindexes_through_log_event(db_session):
    """End-to-end: the game's own authoritative status-change write path
    (set_organization_status) must, by itself, keep the retrieval index
    from continuing to surface a dissolved organization as ACTIVE — no
    caller needs to remember to call the retrieval layer directly."""
    campaign = create_campaign(db_session, "Dissolucao Automatica")
    organization = _create_org(db_session, campaign.id)
    index_organization(db_session, organization)
    reindex_organization_current_state(db_session, organization, occurred_world_minute=0)

    set_organization_status(db_session, organization, OrganizationStatus.DISBANDED)

    current = documents_for_source(
        db_session, campaign.id, KnowledgeSourceType.ORGANIZATION, organization.id
    )
    current_state = next(doc for doc in current if doc.document_type == KnowledgeDocumentType.CURRENT_STATE.value)
    assert "DISBANDED" in current_state.text

    historical = documents_historical(db_session, campaign.id)
    assert any("status ACTIVE" in doc.text for doc in historical)
