"""Phase 23D-E — VisualAsset model."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.enums import VisualAssetValidationStatus
from app.db.models.visual_asset import VisualAsset
from app.game.world.seed import create_campaign


def _asset(**overrides) -> VisualAsset:
    params = dict(
        entity_type="npc",
        entity_id="npc_mira",
        asset_type="NPC_PORTRAIT",
        storage_path="npcs/npc_mira/NPC_PORTRAIT/vasset_abc123.png",
        mime_type="image/png",
        width=1024,
        height=1024,
        workflow_key="EVERREACH_NPC_PORTRAIT",
        workflow_version="V1",
        model_identifier="flux-2-klein-4b",
        seed=5002,
    )
    params.update(overrides)
    return VisualAsset(**params)


def test_creating_a_visual_asset_persists_with_safe_defaults(db_session):
    campaign = create_campaign(db_session, "Visual Asset Defaults", world_seed=301)

    asset = _asset(campaign_id=campaign.id)
    db_session.add(asset)
    db_session.commit()

    stored = db_session.get(VisualAsset, asset.id)
    assert stored.id.startswith("vasset_")
    assert stored.validation_status == VisualAssetValidationStatus.UNREVIEWED
    assert stored.is_current is True
    assert stored.is_canonical_reference is False
    assert stored.created_at is not None


def test_visual_asset_campaign_id_is_optional_for_global_assets(db_session):
    asset = _asset(campaign_id=None, entity_type="item_definition", entity_id="item_sword", asset_type="ITEM_ILLUSTRATION")
    db_session.add(asset)
    db_session.commit()

    stored = db_session.get(VisualAsset, asset.id)
    assert stored.campaign_id is None


def test_visual_asset_rejects_an_unknown_campaign_id(db_session):
    asset = _asset(campaign_id="campaign_inexistente")
    db_session.add(asset)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_superseded_and_current_assets_coexist_for_the_same_entity(db_session):
    campaign = create_campaign(db_session, "Visual Asset Versions", world_seed=302)

    old = _asset(campaign_id=campaign.id, is_current=False)
    new = _asset(campaign_id=campaign.id, is_current=True)
    db_session.add_all([old, new])
    db_session.commit()

    rows = (
        db_session.query(VisualAsset)
        .filter(VisualAsset.campaign_id == campaign.id, VisualAsset.entity_id == "npc_mira")
        .all()
    )
    assert {row.is_current for row in rows} == {True, False}
