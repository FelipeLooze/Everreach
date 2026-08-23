"""Phase 23D-D — Visual Generation Request lifecycle."""
import pytest

from app.core.enums import VisualGenerationRequestStatus
from app.game.visual.generation_request import (
    create_request,
    get_request,
    mark_completed,
    mark_failed,
    mark_in_progress,
)
from app.game.visual.spec import FutureAssetKindError
from app.game.world.seed import create_campaign


def _create(db_session, campaign_id, **overrides):
    params = dict(
        entity_type="npc",
        entity_id="npc_mira",
        asset_type="NPC_PORTRAIT",
        workflow_key="EVERREACH_NPC_PORTRAIT",
        workflow_version="V1",
        campaign_id=campaign_id,
    )
    params.update(overrides)
    return create_request(db_session, **params)


def test_create_request_starts_pending_with_no_result_or_error(db_session):
    campaign = create_campaign(db_session, "Visual Gen Pending", world_seed=201)

    request = _create(db_session, campaign.id)

    assert request.status == VisualGenerationRequestStatus.PENDING
    assert request.result_asset_id is None
    assert request.error_code is None
    assert request.error_message is None
    assert request.id.startswith("vgen_")


def test_create_request_rejects_an_unknown_asset_type(db_session):
    campaign = create_campaign(db_session, "Visual Gen Bad Type", world_seed=202)

    with pytest.raises(FutureAssetKindError):
        _create(db_session, campaign.id, asset_type="NPC_SELFIE")


def test_request_is_campaign_global_when_no_campaign_given(db_session):
    request = _create(db_session, campaign_id=None)

    assert request.campaign_id is None
    assert get_request(db_session, request.id) is not None


def test_mark_in_progress_transitions_status(db_session):
    campaign = create_campaign(db_session, "Visual Gen In Progress", world_seed=203)
    request = _create(db_session, campaign.id)

    updated = mark_in_progress(db_session, request.id)

    assert updated.status == VisualGenerationRequestStatus.IN_PROGRESS
    assert get_request(db_session, request.id).status == VisualGenerationRequestStatus.IN_PROGRESS


def test_mark_completed_sets_result_and_clears_any_prior_error(db_session):
    campaign = create_campaign(db_session, "Visual Gen Completed", world_seed=204)
    request = _create(db_session, campaign.id)
    mark_failed(db_session, request.id, "COMFYUI_OFFLINE", "was offline")

    updated = mark_completed(db_session, request.id, "vasset_abc123")

    assert updated.status == VisualGenerationRequestStatus.COMPLETED
    assert updated.result_asset_id == "vasset_abc123"
    assert updated.error_code is None
    assert updated.error_message is None


def test_mark_failed_records_error_code_and_message(db_session):
    campaign = create_campaign(db_session, "Visual Gen Failed", world_seed=205)
    request = _create(db_session, campaign.id)

    updated = mark_failed(db_session, request.id, "GENERATION_TIMEOUT", "took too long")

    assert updated.status == VisualGenerationRequestStatus.FAILED
    assert updated.error_code == "GENERATION_TIMEOUT"
    assert updated.error_message == "took too long"
    assert updated.result_asset_id is None


def test_get_request_returns_none_for_unknown_id(db_session):
    assert get_request(db_session, "vgen_does_not_exist") is None


def test_mark_in_progress_raises_for_unknown_id(db_session):
    with pytest.raises(ValueError):
        mark_in_progress(db_session, "vgen_does_not_exist")


def test_a_request_never_creates_or_touches_a_visual_identity_row(db_session):
    """A generation request attempt must never itself be read as Canon —
    it must not, as a side effect, create/alter the entity's
    VisualIdentity row (that link only happens once VisualAssetService
    (23D-I) explicitly decides to record a result)."""
    from app.game.visual.spec import get_visual_spec

    campaign = create_campaign(db_session, "Visual Gen No Canon Side Effect", world_seed=206)

    _create(db_session, campaign.id)

    spec = get_visual_spec(db_session, "npc", "npc_mira", campaign_id=campaign.id)
    assert spec.stable == {}
    assert spec.current == {}
    assert spec.assets == {}
