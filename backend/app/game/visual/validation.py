"""Phase 23D-M — Visual Validation State.

validation_status (added to VisualAsset in 23D-E) tracks whether a
human has reviewed a generated asset — UNREVIEWED until someone looks
at it, then VALID or INVALID. This is deliberately distinct from
VisualGenerationRequestStatus (23D-D): a request can COMPLETE
successfully and still produce an asset nobody has reviewed yet, and a
long-since-COMPLETED request's asset can later be marked INVALID
without touching the request record at all — "did the attempt
succeed" and "is the result actually good" are independent axes.

Marking an asset INVALID also clears its is_current flag: a rejected
generation must stop being what a player is shown, even though nothing
here decides what (if anything) becomes current in its place — that is
a separate, deliberate act (a fresh generation via 23D-I, or an
explicit restore via app.game.visual.versioning) rather than an
automatic promotion this module would have to guess at. Marking VALID
has no side effect: it only confirms what is already being shown.
"""
from sqlalchemy.orm import Session

from app.core.enums import VisualAssetValidationStatus
from app.db.models.visual_asset import VisualAsset

_VALID_STATUSES = (
    VisualAssetValidationStatus.UNREVIEWED,
    VisualAssetValidationStatus.VALID,
    VisualAssetValidationStatus.INVALID,
)


class VisualAssetValidationError(ValueError):
    pass


def set_validation_status(db: Session, asset_id: str, status: str) -> VisualAsset:
    if status not in _VALID_STATUSES:
        raise VisualAssetValidationError(f"Unknown validation status: {status!r}")

    asset = db.get(VisualAsset, asset_id)
    if asset is None:
        raise VisualAssetValidationError(f"No VisualAsset with id {asset_id!r}.")

    asset.validation_status = status
    if status == VisualAssetValidationStatus.INVALID:
        asset.is_current = False
    db.flush()
    return asset


def mark_valid(db: Session, asset_id: str) -> VisualAsset:
    return set_validation_status(db, asset_id, VisualAssetValidationStatus.VALID)


def mark_invalid(db: Session, asset_id: str) -> VisualAsset:
    return set_validation_status(db, asset_id, VisualAssetValidationStatus.INVALID)
