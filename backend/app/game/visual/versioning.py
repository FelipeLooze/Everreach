"""Phase 23D-L — Asset Versioning.

"Never overwrite in place" (spec, mandatory): a new VisualAsset for the
same (campaign, entity_type, entity_id, asset_type) is always a NEW
row (23D-I's request_visual_asset never mutates an old one to hold new
content). supersede_current_assets demotes whichever row(s) were
previously is_current=True for that key to is_current=False instead —
every past generation stays on file and in the database as history,
retrievable via list_asset_history.
"""
from sqlalchemy.orm import Session

from app.db.models.visual_asset import VisualAsset


def supersede_current_assets(
    db: Session,
    campaign_id: str | None,
    entity_type: str,
    entity_id: str,
    asset_type: str,
    *,
    keep_current_id: str,
) -> list[VisualAsset]:
    """Mark every OTHER current asset for this (entity, asset_type) as
    superseded, leaving keep_current_id (the newly materialized asset)
    as the only current one. Returns the superseded rows."""
    others = (
        db.query(VisualAsset)
        .filter(
            VisualAsset.campaign_id == campaign_id,
            VisualAsset.entity_type == entity_type,
            VisualAsset.entity_id == entity_id,
            VisualAsset.asset_type == asset_type,
            VisualAsset.is_current.is_(True),
            VisualAsset.id != keep_current_id,
        )
        .all()
    )
    for asset in others:
        asset.is_current = False
    db.flush()
    return others


def get_current_asset(
    db: Session, campaign_id: str | None, entity_type: str, entity_id: str, asset_type: str
) -> VisualAsset | None:
    return (
        db.query(VisualAsset)
        .filter(
            VisualAsset.campaign_id == campaign_id,
            VisualAsset.entity_type == entity_type,
            VisualAsset.entity_id == entity_id,
            VisualAsset.asset_type == asset_type,
            VisualAsset.is_current.is_(True),
        )
        .order_by(VisualAsset.created_at.desc())
        .first()
    )


def list_asset_history(
    db: Session, campaign_id: str | None, entity_type: str, entity_id: str, asset_type: str
) -> list[VisualAsset]:
    """Every asset ever materialized for this key, newest first —
    current and superseded alike."""
    return (
        db.query(VisualAsset)
        .filter(
            VisualAsset.campaign_id == campaign_id,
            VisualAsset.entity_type == entity_type,
            VisualAsset.entity_id == entity_id,
            VisualAsset.asset_type == asset_type,
        )
        .order_by(VisualAsset.created_at.desc())
        .all()
    )
