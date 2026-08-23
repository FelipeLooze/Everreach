"""Phase 23D-J — Status & Failure Handling: bounded retry policy.

Only failures that are plausibly transient (ComfyUI was briefly
unreachable, a generation ran long, or something unclassified went
wrong once) are ever retried. Failures that reflect a real
configuration or Canon problem — WORKFLOW_NOT_FOUND, MODEL_MISSING,
COMFYUI_REJECTED_WORKFLOW, OUTPUT_NOT_FOUND, INVALID_OUTPUT,
FILE_COPY_FAILED — need a human or a config fix, not a blind retry;
retrying those would just burn GPU time reproducing the same failure.

Each retry creates a NEW VisualGenerationRequest row ("REQUEST IS NOT
ASSET", spec, mandatory: an attempt record is never rewritten into a
different attempt) — attempt_count (23D-J's own column addition to
that table) tracks how many attempts a given generation has gone
through so far, bounded by MAX_RETRY_ATTEMPTS.
"""
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import VisualGenerationErrorCode, VisualGenerationRequestStatus
from app.db.models.visual_generation_request import VisualGenerationRequest
from app.game.visual.comfyui_client import ComfyUIClient
from app.game.visual.service import request_visual_asset

MAX_RETRY_ATTEMPTS = 3

RETRYABLE_ERROR_CODES = frozenset(
    {
        VisualGenerationErrorCode.COMFYUI_OFFLINE,
        VisualGenerationErrorCode.GENERATION_TIMEOUT,
        VisualGenerationErrorCode.UNKNOWN_ERROR,
    }
)


class RetryNotAllowedError(ValueError):
    pass


def can_retry(request: VisualGenerationRequest) -> bool:
    return (
        request.status == VisualGenerationRequestStatus.FAILED
        and request.error_code in RETRYABLE_ERROR_CODES
        and request.attempt_count < MAX_RETRY_ATTEMPTS
    )


def retry_visual_asset_request(
    db: Session,
    comfyui_client: ComfyUIClient,
    failed_request_id: str,
    *,
    prompt_text: str,
    reference_image: str | None = None,
    settings: Settings | None = None,
) -> VisualGenerationRequest:
    """Re-attempt a FAILED, retry-eligible request with the same entity/
    asset/workflow/seed. prompt_text (and reference_image, for identity-
    editing workflows) must be supplied again: a FAILED request never
    produced a VisualAsset, so there is nothing to read provenance back
    from — the caller's own visual-spec resolution is still the source
    of truth (matches resolve_*_appearance's "recompute, don't cache"
    stance elsewhere in this codebase)."""
    failed_request = db.get(VisualGenerationRequest, failed_request_id)
    if failed_request is None:
        raise RetryNotAllowedError(f"No VisualGenerationRequest with id {failed_request_id!r}.")
    if not can_retry(failed_request):
        raise RetryNotAllowedError(
            f"Request {failed_request_id!r} is not eligible for retry "
            f"(status={failed_request.status}, error_code={failed_request.error_code}, "
            f"attempt_count={failed_request.attempt_count})."
        )

    return request_visual_asset(
        db,
        comfyui_client,
        entity_type=failed_request.entity_type,
        entity_id=failed_request.entity_id,
        asset_type=failed_request.asset_type,
        workflow_key=failed_request.workflow_key,
        workflow_version=failed_request.workflow_version,
        prompt_text=prompt_text,
        seed=failed_request.seed,
        campaign_id=failed_request.campaign_id,
        reference_image=reference_image,
        settings=settings,
        attempt_count=failed_request.attempt_count + 1,
    )
