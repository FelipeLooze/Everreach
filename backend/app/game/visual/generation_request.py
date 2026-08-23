"""Phase 23D-D — Visual Generation Request lifecycle helpers.

Mirrors app.game.visual.spec's own shape (thin functions wrapping one
table, not a raw-ORM-everywhere convention): every caller that creates
or transitions a VisualGenerationRequest should go through here rather
than mutating the row directly, so the PENDING -> IN_PROGRESS ->
COMPLETED/FAILED lifecycle stays in one place. Orchestration itself
(actually calling ComfyUI) is 23D-I's job, not this module's — this is
only the request record's bookkeeping.
"""
from sqlalchemy.orm import Session

from app.core.enums import VisualGenerationRequestStatus
from app.db.models.visual_generation_request import VisualGenerationRequest
from app.game.visual.spec import FUTURE_ASSET_KINDS, FutureAssetKindError


def create_request(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    asset_type: str,
    workflow_key: str,
    workflow_version: str,
    campaign_id: str | None = None,
    seed: int | None = None,
    attempt_count: int = 1,
) -> VisualGenerationRequest:
    """Create a new PENDING request. Does not deduplicate against an
    existing in-flight request for the same entity/asset_type — that
    check belongs to 23D-K, which decides what "in-flight" means for a
    given caller; this function only ever creates.

    attempt_count defaults to 1 (a first attempt); app.game.visual.
    retry_policy passes a higher value when this request is itself a
    retry of an earlier FAILED one."""
    if asset_type not in FUTURE_ASSET_KINDS:
        raise FutureAssetKindError(f"Unknown future asset kind: {asset_type!r}")

    request = VisualGenerationRequest(
        campaign_id=campaign_id,
        entity_type=entity_type,
        entity_id=entity_id,
        asset_type=asset_type,
        workflow_key=workflow_key,
        workflow_version=workflow_version,
        seed=seed,
        attempt_count=attempt_count,
        status=VisualGenerationRequestStatus.PENDING,
    )
    db.add(request)
    db.flush()
    return request


def get_request(db: Session, request_id: str) -> VisualGenerationRequest | None:
    return db.get(VisualGenerationRequest, request_id)


def mark_in_progress(db: Session, request_id: str) -> VisualGenerationRequest:
    request = _require_request(db, request_id)
    request.status = VisualGenerationRequestStatus.IN_PROGRESS
    db.flush()
    return request


def mark_completed(db: Session, request_id: str, result_asset_id: str) -> VisualGenerationRequest:
    request = _require_request(db, request_id)
    request.status = VisualGenerationRequestStatus.COMPLETED
    request.result_asset_id = result_asset_id
    request.error_code = None
    request.error_message = None
    db.flush()
    return request


def mark_failed(
    db: Session, request_id: str, error_code: str, error_message: str
) -> VisualGenerationRequest:
    request = _require_request(db, request_id)
    request.status = VisualGenerationRequestStatus.FAILED
    request.error_code = error_code
    request.error_message = error_message
    db.flush()
    return request


def _require_request(db: Session, request_id: str) -> VisualGenerationRequest:
    request = get_request(db, request_id)
    if request is None:
        raise ValueError(f"No VisualGenerationRequest with id {request_id!r}")
    return request
