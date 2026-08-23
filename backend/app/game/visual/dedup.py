"""Phase 23D-K — Deduplication & Reuse.

Two independent dedup concerns, kept separate on purpose:

1. IN-FLIGHT dedup: prevent duplicate GPU work from a player simply
   reopening a UI panel while a generation is already running for the
   same entity/asset_type. find_in_flight_request() reuses the exact
   index 23D-D's own VisualGenerationRequest table was built with
   (campaign_id, entity_type, entity_id, asset_type, status).

2. CONTENT dedup: skip generating an asset that would be identical to
   one already on file. compute_spec_fingerprint() hashes exactly the
   inputs that actually determine ComfyUI's output (prompt text,
   workflow identity, seed, and — for identity-preserving edits — the
   reference image); find_reusable_asset() looks for a CURRENT
   VisualAsset whose stored fingerprint already matches.

Neither function calls ComfyUI or creates anything — both are pure
read-side lookups app.game.visual.service.request_visual_asset consults
BEFORE deciding whether generation is actually needed.
"""
import hashlib

from sqlalchemy.orm import Session

from app.core.enums import VisualGenerationRequestStatus
from app.db.models.visual_asset import VisualAsset
from app.db.models.visual_generation_request import VisualGenerationRequest

_IN_FLIGHT_STATUSES = (
    VisualGenerationRequestStatus.PENDING,
    VisualGenerationRequestStatus.IN_PROGRESS,
)


def compute_spec_fingerprint(
    *,
    prompt_text: str,
    workflow_key: str,
    workflow_version: str,
    seed: int,
    reference_image: str | None = None,
) -> str:
    """A stable hash of exactly the inputs that determine ComfyUI's
    output for one generation. Any change to prompt text, which
    workflow/version, the seed, or (for an identity-preserving edit)
    the reference image is a genuine content change and must produce a
    different fingerprint; nothing else (timestamps, request ids, ...)
    is part of it."""
    payload = "\x1f".join(
        [workflow_key, workflow_version, str(seed), prompt_text, reference_image or ""]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_in_flight_request(
    db: Session, campaign_id: str | None, entity_type: str, entity_id: str, asset_type: str
) -> VisualGenerationRequest | None:
    return (
        db.query(VisualGenerationRequest)
        .filter(
            VisualGenerationRequest.campaign_id == campaign_id,
            VisualGenerationRequest.entity_type == entity_type,
            VisualGenerationRequest.entity_id == entity_id,
            VisualGenerationRequest.asset_type == asset_type,
            VisualGenerationRequest.status.in_(_IN_FLIGHT_STATUSES),
        )
        .order_by(VisualGenerationRequest.created_at.desc())
        .first()
    )


def find_reusable_asset(
    db: Session,
    campaign_id: str | None,
    entity_type: str,
    entity_id: str,
    asset_type: str,
    spec_fingerprint: str,
) -> VisualAsset | None:
    return (
        db.query(VisualAsset)
        .filter(
            VisualAsset.campaign_id == campaign_id,
            VisualAsset.entity_type == entity_type,
            VisualAsset.entity_id == entity_id,
            VisualAsset.asset_type == asset_type,
            VisualAsset.is_current.is_(True),
            VisualAsset.spec_fingerprint == spec_fingerprint,
        )
        .order_by(VisualAsset.created_at.desc())
        .first()
    )
