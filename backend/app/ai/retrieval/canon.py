"""Phase 18B — Canon Knowledge Index population for the core geographic
and social entity classes (Region/Subregion/Settlement/Location/
Organization). Deliberately NOT every entity class the spec lists
(Route/RegionalBoundary/Business/Item/Technique/Quest) — those have no
rich free-text canon worth indexing yet ("do not index every database
row blindly"); NPC per-entity chunking is Phase 18D's own subphase.

Each indexer writes exactly one IDENTITY document per entity, built only
from that entity's own already-canonical free-text fields — no new lore
is invented here. Indexing is unconditional (every Region/Settlement/...
gets a document); Phase 18I's knowledge-aware filtering is what decides
whether a given knower is ever allowed to see it, not this module.
"""
from sqlalchemy.orm import Session

from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.ai.retrieval.documents import upsert_document
from app.db.models.knowledge_index import IndexedKnowledgeDocument
from app.db.models.location import Location
from app.db.models.organization import Organization
from app.db.models.region import Region
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion


def index_region(db: Session, region: Region) -> IndexedKnowledgeDocument:
    text = f"{region.name}. {region.description}".strip()
    document = upsert_document(
        db,
        region.campaign_id,
        KnowledgeSourceType.REGION,
        region.id,
        KnowledgeDocumentType.IDENTITY,
        text,
    )
    if region.historical_summary:
        upsert_document(
            db,
            region.campaign_id,
            KnowledgeSourceType.REGION,
            region.id,
            KnowledgeDocumentType.BACKGROUND,
            f"{region.name}: {region.historical_summary}",
        )
    return document


def index_subregion(db: Session, subregion: Subregion) -> IndexedKnowledgeDocument | None:
    region = db.get(Region, subregion.region_id)
    if region is None:
        return None
    text = (
        f"{subregion.name} (parte da região {region.name}). "
        f"Bioma: {subregion.biome}. Perigo: {subregion.danger_level}. "
        f"Cultura: {subregion.culture_summary or 'sem registro'}. "
        f"Economia: {subregion.economy_summary or 'sem registro'}."
    )
    return upsert_document(
        db,
        region.campaign_id,
        KnowledgeSourceType.SUBREGION,
        subregion.id,
        KnowledgeDocumentType.IDENTITY,
        text,
    )


def index_settlement(db: Session, settlement: Settlement) -> IndexedKnowledgeDocument | None:
    location = db.get(Location, settlement.location_id)
    if location is None:
        return None
    region = db.get(Region, location.region_id)
    if region is None:
        return None
    text = (
        f"{location.name} ({settlement.settlement_type}). "
        f"{location.description or 'Sem descrição registrada.'} "
        f"{settlement.profile}".strip()
    )
    return upsert_document(
        db,
        region.campaign_id,
        KnowledgeSourceType.SETTLEMENT,
        settlement.id,
        KnowledgeDocumentType.IDENTITY,
        text,
    )


def index_location(db: Session, location: Location) -> IndexedKnowledgeDocument | None:
    region = db.get(Region, location.region_id)
    if region is None:
        return None
    text = f"{location.name} ({location.type}). {location.description}".strip()
    return upsert_document(
        db,
        region.campaign_id,
        KnowledgeSourceType.LOCATION,
        location.id,
        KnowledgeDocumentType.IDENTITY,
        text,
    )


def index_organization(db: Session, organization: Organization) -> IndexedKnowledgeDocument:
    text = (
        f"{organization.name} ({organization.organization_type}). "
        f"{organization.description or 'Sem descrição registrada.'}"
    )
    document = upsert_document(
        db,
        organization.campaign_id,
        KnowledgeSourceType.ORGANIZATION,
        organization.id,
        KnowledgeDocumentType.IDENTITY,
        text,
    )
    upsert_document(
        db,
        organization.campaign_id,
        KnowledgeSourceType.ORGANIZATION,
        organization.id,
        KnowledgeDocumentType.CURRENT_STATE,
        f"{organization.name}: status {organization.status}, visibilidade {organization.visibility}.",
    )
    return document
