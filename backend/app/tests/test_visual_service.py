"""Phase 23D-I — Generation Orchestration."""
import json
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import Settings
from app.core.enums import VisualGenerationRequestStatus
from app.db.models.visual_asset import VisualAsset
from app.db.models.visual_generation_request import VisualGenerationRequest
from app.game.visual.comfyui_client import ComfyUIClient, ComfyUIClientError
from app.game.visual.service import request_visual_asset
from app.game.visual.workflow_registry import WorkflowNotFoundError
from app.game.world.seed import create_campaign


class FakeComfyUIClient(ComfyUIClient):
    def __init__(
        self,
        *,
        available: bool = True,
        submit_error: ComfyUIClientError | None = None,
        wait_error: ComfyUIClientError | None = None,
        history_entry: dict | None = None,
        output_path: Path | None = None,
        assert_committed_in_progress: tuple | None = None,
    ) -> None:
        self._available = available
        self._submit_error = submit_error
        self._wait_error = wait_error
        self._history_entry = history_entry if history_entry is not None else {"outputs": {}}
        self._output_path = output_path
        # (db_session, campaign_id) — if given, wait_for_completion looks
        # up this campaign's request from the SAME session and asserts it
        # is already IN_PROGRESS, proving that state was committed before
        # this (simulated) blocking call happened.
        self._assert_committed_in_progress = assert_committed_in_progress

    def is_available(self) -> bool:
        return self._available

    def system_stats(self) -> dict:
        return {}

    def submit_workflow(self, graph: dict, client_id: str) -> str:
        if self._submit_error is not None:
            raise self._submit_error
        return "prompt_1"

    def get_queue(self) -> dict:
        return {}

    def get_history(self, prompt_id: str) -> dict | None:
        return self._history_entry

    def wait_for_completion(self, prompt_id: str, timeout_seconds: float | None = None) -> dict:
        if self._assert_committed_in_progress is not None:
            db_session, campaign_id = self._assert_committed_in_progress
            request = (
                db_session.query(VisualGenerationRequest)
                .filter(VisualGenerationRequest.campaign_id == campaign_id)
                .one()
            )
            assert request.status == VisualGenerationRequestStatus.IN_PROGRESS
        if self._wait_error is not None:
            raise self._wait_error
        return self._history_entry

    def resolve_output_path(self, subfolder: str, filename: str) -> Path:
        return self._output_path


def _write_item_workflow(workflow_root: Path) -> None:
    workflow_root.mkdir(parents=True, exist_ok=True)
    graph = {
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-4b.safetensors"}},
        "20": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder"}},
        "31": {"class_type": "RandomNoise", "inputs": {"noise_seed": 1}},
        "41": {"class_type": "SaveImage", "inputs": {"filename_prefix": "placeholder"}},
    }
    (workflow_root / "EVERREACH_ITEM_V3_API.json").write_text(json.dumps(graph), encoding="utf-8")


def _settings(tmp_path: Path, *, with_workflow: bool = True) -> Settings:
    workflow_root = tmp_path / "workflows"
    asset_root = tmp_path / "assets"
    if with_workflow:
        _write_item_workflow(workflow_root)
    else:
        workflow_root.mkdir(parents=True, exist_ok=True)
    return Settings(comfyui_workflow_root=str(workflow_root), comfyui_asset_root=str(asset_root))


def _raw_output_image(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw_output"
    raw_dir.mkdir(exist_ok=True)
    path = raw_dir / "ComfyUI_00001_.png"
    Image.new("RGB", (64, 48), color="blue").save(path)
    return path


def _request(**overrides) -> dict:
    params = dict(
        entity_type="item_definition",
        entity_id="item_sword",
        asset_type="ITEM_ILLUSTRATION",
        workflow_key="EVERREACH_ITEM",
        workflow_version="V3",
        prompt_text="a prompt",
        seed=5001,
    )
    params.update(overrides)
    return params


def test_request_visual_asset_completes_successfully(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Success", world_seed=501)
    raw_image = _raw_output_image(tmp_path)
    client = FakeComfyUIClient(
        history_entry={"outputs": {"41": {"images": [{"subfolder": "x", "filename": "y.png"}]}}},
        output_path=raw_image,
    )

    request = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings, **_request()
    )

    assert request.status == VisualGenerationRequestStatus.COMPLETED
    assert request.result_asset_id is not None
    asset = db_session.get(VisualAsset, request.result_asset_id)
    assert asset is not None
    assert asset.width == 64
    assert asset.height == 48
    assert asset.mime_type == "image/png"
    assert asset.workflow_key == "EVERREACH_ITEM"
    assert asset.workflow_version == "V3"
    assert asset.model_identifier == "flux-2-klein-4b.safetensors"
    assert asset.campaign_id == campaign.id
    stored_path = tmp_path / "assets" / asset.storage_path
    assert stored_path.is_file()


def test_request_visual_asset_fails_when_comfyui_is_offline(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Offline", world_seed=502)
    client = FakeComfyUIClient(available=False)

    request = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings, **_request()
    )

    assert request.status == VisualGenerationRequestStatus.FAILED
    assert request.error_code == "COMFYUI_OFFLINE"
    assert request.result_asset_id is None


def test_request_visual_asset_fails_when_workflow_file_is_missing_on_disk(db_session, tmp_path):
    settings = _settings(tmp_path, with_workflow=False)
    campaign = create_campaign(db_session, "Visual Service Missing File", world_seed=503)
    client = FakeComfyUIClient()

    request = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings, **_request()
    )

    assert request.status == VisualGenerationRequestStatus.FAILED
    assert request.error_code == "WORKFLOW_NOT_FOUND"


def test_request_visual_asset_raises_immediately_for_an_unregistered_workflow(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Bad Workflow", world_seed=504)
    client = FakeComfyUIClient()

    with pytest.raises(WorkflowNotFoundError):
        request_visual_asset(
            db_session, client, campaign_id=campaign.id, settings=settings,
            **_request(workflow_key="NOT_A_WORKFLOW"),
        )

    assert db_session.query(VisualGenerationRequest).count() == 0


def test_request_visual_asset_fails_on_comfyui_rejection(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Rejected", world_seed=505)
    client = FakeComfyUIClient(submit_error=ComfyUIClientError("ComfyUI rejected the workflow: bad node"))

    request = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings, **_request()
    )

    assert request.status == VisualGenerationRequestStatus.FAILED
    assert request.error_code == "COMFYUI_REJECTED_WORKFLOW"


def test_request_visual_asset_classifies_a_missing_model_rejection_distinctly(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Model Missing", world_seed=510)
    client = FakeComfyUIClient(
        submit_error=ComfyUIClientError(
            "ComfyUI rejected the workflow: Value not in list: unet_name: "
            "'flux-2-klein-4b.safetensors' not in [...]"
        )
    )

    request = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings, **_request()
    )

    assert request.status == VisualGenerationRequestStatus.FAILED
    assert request.error_code == "MODEL_MISSING"


def test_request_visual_asset_fails_on_timeout(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Timeout", world_seed=506)
    client = FakeComfyUIClient(wait_error=ComfyUIClientError("ComfyUI took too long to respond."))

    request = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings, **_request()
    )

    assert request.status == VisualGenerationRequestStatus.FAILED
    assert request.error_code == "GENERATION_TIMEOUT"


def test_request_visual_asset_fails_when_no_output_image_is_present(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service No Output", world_seed=507)
    client = FakeComfyUIClient(history_entry={"outputs": {}})

    request = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings, **_request()
    )

    assert request.status == VisualGenerationRequestStatus.FAILED
    assert request.error_code == "OUTPUT_NOT_FOUND"


def test_request_visual_asset_fails_when_raw_file_copy_fails(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Copy Fails", world_seed=508)
    client = FakeComfyUIClient(
        history_entry={"outputs": {"41": {"images": [{"subfolder": "x", "filename": "y.png"}]}}},
        output_path=tmp_path / "does_not_exist.png",
    )

    request = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings, **_request()
    )

    assert request.status == VisualGenerationRequestStatus.FAILED
    assert request.error_code == "FILE_COPY_FAILED"


def test_request_visual_asset_commits_in_progress_before_calling_comfyui(db_session, tmp_path):
    """"DO NOT keep a database transaction open while waiting for
    ComfyUI" (spec, mandatory) — proven here by having the fake client
    itself read the request's status back from the same session inside
    wait_for_completion: it must already be IN_PROGRESS and committed
    before the (simulated) blocking call happens."""
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Ordering", world_seed=509)
    raw_image = _raw_output_image(tmp_path)
    client = FakeComfyUIClient(
        history_entry={"outputs": {"41": {"images": [{"subfolder": "x", "filename": "y.png"}]}}},
        output_path=raw_image,
        assert_committed_in_progress=(db_session, campaign.id),
    )

    request = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings, **_request()
    )

    assert request.status == VisualGenerationRequestStatus.COMPLETED


def test_request_visual_asset_returns_an_existing_in_flight_request_instead_of_a_duplicate(
    db_session, tmp_path
):
    """23D-K in-flight dedup, simulated by inserting a PENDING row
    directly for this entity/asset_type (as if an earlier call left one
    running) rather than actually blocking a real request mid-flight."""
    from app.game.visual.generation_request import create_request

    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service In Flight Dedup", world_seed=511)
    in_flight = create_request(
        db_session, entity_type="item_definition", entity_id="item_dup", asset_type="ITEM_ILLUSTRATION",
        workflow_key="EVERREACH_ITEM", workflow_version="V3", campaign_id=campaign.id, seed=5001,
    )
    db_session.commit()

    class _NeverSubmitsClient(FakeComfyUIClient):
        def submit_workflow(self, graph, client_id):
            raise AssertionError("should never submit while a request is already in flight")

    result = request_visual_asset(
        db_session, _NeverSubmitsClient(), campaign_id=campaign.id, settings=settings,
        **_request(entity_id="item_dup"),
    )

    assert result.id == in_flight.id
    assert (
        db_session.query(VisualGenerationRequest)
        .filter(VisualGenerationRequest.entity_id == "item_dup")
        .count()
        == 1
    )


def test_request_visual_asset_reuses_a_matching_asset_without_calling_comfyui(db_session, tmp_path):
    from app.game.visual.dedup import compute_spec_fingerprint

    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Content Dedup", world_seed=512)
    fingerprint = compute_spec_fingerprint(
        prompt_text="a prompt", workflow_key="EVERREACH_ITEM", workflow_version="V3", seed=5001,
    )
    existing_asset = VisualAsset(
        campaign_id=campaign.id, entity_type="item_definition", entity_id="item_reuse",
        asset_type="ITEM_ILLUSTRATION", storage_path="x/y/z.png", mime_type="image/png",
        width=1024, height=1024, workflow_key="EVERREACH_ITEM", workflow_version="V3",
        model_identifier="flux-2-klein-4b", seed=5001, spec_fingerprint=fingerprint,
    )
    db_session.add(existing_asset)
    db_session.commit()

    class _NeverSubmitsClient(FakeComfyUIClient):
        def submit_workflow(self, graph, client_id):
            raise AssertionError("should never submit when a reusable asset already exists")

    result = request_visual_asset(
        db_session, _NeverSubmitsClient(), campaign_id=campaign.id, settings=settings,
        **_request(entity_id="item_reuse"),
    )

    assert result.status == VisualGenerationRequestStatus.COMPLETED
    assert result.result_asset_id == existing_asset.id


def test_request_visual_asset_does_not_reuse_an_asset_with_a_different_fingerprint(db_session, tmp_path):
    from app.game.visual.dedup import compute_spec_fingerprint

    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Visual Service Content Dedup Mismatch", world_seed=513)
    stale_fingerprint = compute_spec_fingerprint(
        prompt_text="an old prompt", workflow_key="EVERREACH_ITEM", workflow_version="V3", seed=999,
    )
    existing_asset = VisualAsset(
        campaign_id=campaign.id, entity_type="item_definition", entity_id="item_changed",
        asset_type="ITEM_ILLUSTRATION", storage_path="x/y/z.png", mime_type="image/png",
        width=1024, height=1024, workflow_key="EVERREACH_ITEM", workflow_version="V3",
        model_identifier="flux-2-klein-4b", seed=999, spec_fingerprint=stale_fingerprint,
    )
    db_session.add(existing_asset)
    db_session.commit()
    raw_image = _raw_output_image(tmp_path)
    client = FakeComfyUIClient(
        history_entry={"outputs": {"41": {"images": [{"subfolder": "x", "filename": "y.png"}]}}},
        output_path=raw_image,
    )

    result = request_visual_asset(
        db_session, client, campaign_id=campaign.id, settings=settings,
        **_request(entity_id="item_changed"),
    )

    assert result.status == VisualGenerationRequestStatus.COMPLETED
    assert result.result_asset_id != existing_asset.id
