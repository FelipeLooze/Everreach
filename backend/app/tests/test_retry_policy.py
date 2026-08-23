"""Phase 23D-J — Status & Failure Handling: bounded retry policy."""
import json
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import Settings
from app.core.enums import VisualGenerationErrorCode, VisualGenerationRequestStatus
from app.db.models.visual_generation_request import VisualGenerationRequest
from app.game.visual.comfyui_client import ComfyUIClient
from app.game.visual.generation_request import create_request, mark_failed
from app.game.visual.retry_policy import (
    MAX_RETRY_ATTEMPTS,
    RetryNotAllowedError,
    can_retry,
    retry_visual_asset_request,
)
from app.game.world.seed import create_campaign


class _FakeComfyUIClient(ComfyUIClient):
    """Minimal always-succeeds stand-in — retry_policy's own tests only
    care about the retry-eligibility bookkeeping, not generation edge
    cases (already covered by app/tests/test_visual_service.py)."""

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path

    def is_available(self) -> bool:
        return True

    def system_stats(self) -> dict:
        return {}

    def submit_workflow(self, graph: dict, client_id: str) -> str:
        return "prompt_1"

    def get_queue(self) -> dict:
        return {}

    def get_history(self, prompt_id: str) -> dict | None:
        return {"outputs": {"41": {"images": [{"subfolder": "x", "filename": "y.png"}]}}}

    def wait_for_completion(self, prompt_id: str, timeout_seconds: float | None = None) -> dict:
        return self.get_history(prompt_id)

    def resolve_output_path(self, subfolder: str, filename: str) -> Path:
        return self._output_path


def _settings(tmp_path: Path) -> Settings:
    workflow_root = tmp_path / "workflows"
    workflow_root.mkdir(parents=True, exist_ok=True)
    graph = {
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-4b.safetensors"}},
        "20": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder"}},
        "31": {"class_type": "RandomNoise", "inputs": {"noise_seed": 1}},
        "41": {"class_type": "SaveImage", "inputs": {"filename_prefix": "placeholder"}},
    }
    (workflow_root / "EVERREACH_ITEM_V3_API.json").write_text(json.dumps(graph), encoding="utf-8")
    return Settings(comfyui_workflow_root=str(workflow_root), comfyui_asset_root=str(tmp_path / "assets"))


def _raw_output_image(tmp_path: Path) -> Path:
    path = tmp_path / "raw_output.png"
    Image.new("RGB", (32, 32), color="red").save(path)
    return path


def _failed_request(db_session, campaign_id, *, error_code, attempt_count=1):
    request = create_request(
        db_session,
        entity_type="item_definition",
        entity_id="item_sword",
        asset_type="ITEM_ILLUSTRATION",
        workflow_key="EVERREACH_ITEM",
        workflow_version="V3",
        campaign_id=campaign_id,
        seed=5001,
        attempt_count=attempt_count,
    )
    db_session.commit()
    mark_failed(db_session, request.id, error_code, "simulated failure")
    db_session.commit()
    return request


def test_can_retry_is_true_for_a_retryable_error_below_the_attempt_cap(db_session):
    campaign = create_campaign(db_session, "Retry Policy Eligible", world_seed=601)
    request = _failed_request(
        db_session, campaign.id, error_code=VisualGenerationErrorCode.COMFYUI_OFFLINE
    )

    assert can_retry(request) is True


@pytest.mark.parametrize(
    "error_code",
    [
        VisualGenerationErrorCode.WORKFLOW_NOT_FOUND,
        VisualGenerationErrorCode.MODEL_MISSING,
        VisualGenerationErrorCode.COMFYUI_REJECTED_WORKFLOW,
        VisualGenerationErrorCode.OUTPUT_NOT_FOUND,
        VisualGenerationErrorCode.INVALID_OUTPUT,
        VisualGenerationErrorCode.FILE_COPY_FAILED,
    ],
)
def test_can_retry_is_false_for_non_transient_error_codes(db_session, error_code):
    campaign = create_campaign(db_session, f"Retry Policy Not Eligible {error_code}", world_seed=602)
    request = _failed_request(db_session, campaign.id, error_code=error_code)

    assert can_retry(request) is False


def test_can_retry_is_false_once_the_attempt_cap_is_reached(db_session):
    campaign = create_campaign(db_session, "Retry Policy Cap", world_seed=603)
    request = _failed_request(
        db_session, campaign.id,
        error_code=VisualGenerationErrorCode.GENERATION_TIMEOUT,
        attempt_count=MAX_RETRY_ATTEMPTS,
    )

    assert can_retry(request) is False


def test_retry_visual_asset_request_creates_a_new_row_with_incremented_attempt_count(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Retry Policy Success", world_seed=604)
    original = _failed_request(
        db_session, campaign.id, error_code=VisualGenerationErrorCode.COMFYUI_OFFLINE
    )
    raw_image = _raw_output_image(tmp_path)
    client = _FakeComfyUIClient(raw_image)

    retried = retry_visual_asset_request(
        db_session, client, original.id, prompt_text="a retried prompt", settings=settings
    )

    assert retried.id != original.id
    assert retried.attempt_count == original.attempt_count + 1
    assert retried.status == VisualGenerationRequestStatus.COMPLETED
    assert db_session.query(VisualGenerationRequest).count() == 2


def test_retry_visual_asset_request_raises_for_a_non_retryable_error_code(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Retry Policy Rejected Not Retryable", world_seed=605)
    original = _failed_request(
        db_session, campaign.id, error_code=VisualGenerationErrorCode.COMFYUI_REJECTED_WORKFLOW
    )
    client = _FakeComfyUIClient(tmp_path / "unused.png")

    with pytest.raises(RetryNotAllowedError):
        retry_visual_asset_request(
            db_session, client, original.id, prompt_text="a retried prompt", settings=settings
        )


def test_retry_visual_asset_request_raises_for_unknown_request_id(db_session, tmp_path):
    settings = _settings(tmp_path)
    client = _FakeComfyUIClient(tmp_path / "unused.png")

    with pytest.raises(RetryNotAllowedError):
        retry_visual_asset_request(
            db_session, client, "vgen_does_not_exist", prompt_text="x", settings=settings
        )


def test_retry_visual_asset_request_raises_once_attempts_are_exhausted(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Retry Policy Exhausted", world_seed=606)
    original = _failed_request(
        db_session, campaign.id,
        error_code=VisualGenerationErrorCode.GENERATION_TIMEOUT,
        attempt_count=MAX_RETRY_ATTEMPTS,
    )
    client = _FakeComfyUIClient(tmp_path / "unused.png")

    with pytest.raises(RetryNotAllowedError):
        retry_visual_asset_request(
            db_session, client, original.id, prompt_text="x", settings=settings
        )
