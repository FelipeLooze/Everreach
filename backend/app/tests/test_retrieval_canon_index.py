"""Phase 18B — Canon Knowledge Index."""

from app.core.enums import (
    KnowledgeDocumentType,
    KnowledgeSourceType,
    OrganizationOrigin,
    OrganizationType,
)
from app.ai.retrieval.canon import (
    index_location,
    index_organization,
    index_region,
    index_settlement,
    index_subregion,
)
from app.ai.retrieval.documents import current_documents, documents_for_source, upsert_document
from app.db.models.location import Location
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def test_upsert_document_is_idempotent_and_only_updates_when_text_changes(db_session):
    campaign = create_campaign(db_session, "Index Idempotente", world_seed=1)

    first = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake",
        KnowledgeDocumentType.IDENTITY, "Texto original.",
    )
    same = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake",
        KnowledgeDocumentType.IDENTITY, "Texto original.",
    )
    changed = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake",
        KnowledgeDocumentType.IDENTITY, "Texto atualizado.",
    )

    assert first.id == same.id == changed.id
    assert changed.text == "Texto atualizado."
    assert documents_for_source(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake"
    ) == [changed]


def test_index_region_creates_identity_and_background_documents(db_session):
    campaign = create_campaign(db_session, "Regiao Indexada", world_seed=2)
    region, _location = seed_initial_region(db_session, campaign.id)
    region.historical_summary = "Uma antiga disputa de fronteira moldou esta terra."
    db_session.flush()

    index_region(db_session, region)

    docs = documents_for_source(db_session, campaign.id, KnowledgeSourceType.REGION, region.id)
    by_type = {doc.document_type: doc for doc in docs}
    assert region.name in by_type[KnowledgeDocumentType.IDENTITY.value].text
    assert "disputa de fronteira" in by_type[KnowledgeDocumentType.BACKGROUND.value].text


def test_index_subregion_settlement_and_location(db_session):
    campaign = create_campaign(db_session, "Geografia Indexada", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)

    subregion = db_session.get(Subregion, village.subregion_id)
    settlement = (
        db_session.query(Settlement).filter(Settlement.location_id == village.id).one()
    )

    subregion_doc = index_subregion(db_session, subregion)
    settlement_doc = index_settlement(db_session, settlement)
    location_doc = index_location(db_session, village)

    assert subregion_doc is not None and subregion.name in subregion_doc.text
    assert settlement_doc is not None and village.name in settlement_doc.text
    assert location_doc is not None and village.name in location_doc.text
    for doc in (subregion_doc, settlement_doc, location_doc):
        assert doc.campaign_id == campaign.id


def test_index_organization_creates_identity_and_current_state(db_session):
    campaign = create_campaign(db_session, "Organizacao Indexada", world_seed=4)
    organization = create_organization(
        db_session, campaign.id, "Guilda dos Mercadores",
        organization_type=OrganizationType.GUILD,
        origin=OrganizationOrigin.NATIVE,
        description="Regula o comércio local.",
    )

    index_organization(db_session, organization)

    docs = documents_for_source(db_session, campaign.id, KnowledgeSourceType.ORGANIZATION, organization.id)
    by_type = {doc.document_type: doc for doc in docs}
    assert "Regula o comércio local" in by_type[KnowledgeDocumentType.IDENTITY.value].text
    assert "status ACTIVE" in by_type[KnowledgeDocumentType.CURRENT_STATE.value].text


def test_current_documents_is_hard_scoped_to_campaign(db_session):
    first = create_campaign(db_session, "Campanha A", world_seed=5)
    second = create_campaign(db_session, "Campanha B", world_seed=6)
    region_a, _ = seed_initial_region(db_session, first.id)
    region_b, _ = seed_initial_region(db_session, second.id)
    index_region(db_session, region_a)
    index_region(db_session, region_b)

    docs = current_documents(db_session, first.id, source_types=[KnowledgeSourceType.REGION])

    assert {doc.source_id for doc in docs} == {region_a.id}


def test_documents_for_source_excludes_non_current_unless_requested(db_session):
    campaign = create_campaign(db_session, "Historico Excluido", world_seed=7)
    document = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake",
        KnowledgeDocumentType.IDENTITY, "Texto.",
    )
    document.is_current = False
    db_session.flush()

    assert documents_for_source(db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake") == []
    assert documents_for_source(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake", include_historical=True
    ) == [document]
