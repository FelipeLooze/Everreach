"""Phase 23D-M — Visual Validation State."""
import pytest

from app.core.enums import VisualAssetValidationStatus
from app.db.models.visual_asset import VisualAsset
from app.game.visual.validation import (
    VisualAssetValidationError,
    mark_invalid,
    mark_valid,
    set_validation_status,
)
from app.game.world.seed import create_campaign


def _asset(campaign_id, **overrides) -> VisualAsset:
    params = dict(
        campaign_id=campaign_id, entity_type="npc", entity_id="npc_mira", asset_type="NPC_PORTRAIT",
        storage_path="npcs/npc_mira/NPC_PORTRAIT/vasset_x.png", mime_type="image/png",
        width=1024, height=1024, workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1",
        model_identifier="flux-2-klein-4b", seed=1,
    )
    params.update(overrides)
    return VisualAsset(**params)


def test_new_asset_defaults_to_unreviewed(db_session):
    campaign = create_campaign(db_session, "Validation Default", world_seed=901)
    asset = _asset(campaign.id)
    db_session.add(asset)
    db_session.commit()

    assert asset.validation_status == VisualAssetValidationStatus.UNREVIEWED


def test_mark_valid_sets_status_and_leaves_is_current_untouched(db_session):
    campaign = create_campaign(db_session, "Validation Valid", world_seed=902)
    asset = _asset(campaign.id, is_current=True)
    db_session.add(asset)
    db_session.commit()

    updated = mark_valid(db_session, asset.id)

    assert updated.validation_status == VisualAssetValidationStatus.VALID
    assert updated.is_current is True


def test_mark_invalid_sets_status_and_clears_is_current(db_session):
    campaign = create_campaign(db_session, "Validation Invalid", world_seed=903)
    asset = _asset(campaign.id, is_current=True)
    db_session.add(asset)
    db_session.commit()

    updated = mark_invalid(db_session, asset.id)

    assert updated.validation_status == VisualAssetValidationStatus.INVALID
    assert updated.is_current is False


def test_mark_invalid_on_an_already_superseded_asset_stays_not_current(db_session):
    campaign = create_campaign(db_session, "Validation Invalid Already Superseded", world_seed=904)
    asset = _asset(campaign.id, is_current=False)
    db_session.add(asset)
    db_session.commit()

    updated = mark_invalid(db_session, asset.id)

    assert updated.is_current is False


def test_set_validation_status_raises_for_an_unknown_status(db_session):
    campaign = create_campaign(db_session, "Validation Unknown Status", world_seed=905)
    asset = _asset(campaign.id)
    db_session.add(asset)
    db_session.commit()

    with pytest.raises(VisualAssetValidationError):
        set_validation_status(db_session, asset.id, "SUPER_VALID")


def test_set_validation_status_raises_for_an_unknown_asset(db_session):
    with pytest.raises(VisualAssetValidationError):
        set_validation_status(db_session, "vasset_does_not_exist", VisualAssetValidationStatus.VALID)


def test_validation_status_persists_across_reads(db_session):
    campaign = create_campaign(db_session, "Validation Persists", world_seed=906)
    asset = _asset(campaign.id)
    db_session.add(asset)
    db_session.commit()
    mark_valid(db_session, asset.id)

    reread = db_session.get(VisualAsset, asset.id)

    assert reread.validation_status == VisualAssetValidationStatus.VALID
