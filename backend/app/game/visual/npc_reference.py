"""Phase 23D-H — NPC Canonical Reference Support.

"NPC canonical reference vs current-portrait distinction" (spec,
mandatory): the CANONICAL REFERENCE is the fixed identity-anchor image
every future identity-preserving edit (the EVERREACH_NPC_IDENTITY
workflow's LoadImage input, see app.game.visual.prompt_builder.
inject_workflow_parameters' reference_image parameter) must be built
from. It changes only on a deliberate, rare re-anchoring — e.g. an
NPC visibly aging in-world, producing a reference_v2. The CURRENT
PORTRAIT is whatever NPC_PORTRAIT asset is presently shown to the
player, which can change far more often (a clothing/state variant).
These are represented by two independent VisualAsset flags
(is_canonical_reference, is_current) on purpose — conflating them
would make an ordinary clothing-variant regenerate silently break every
future identity-preserving edit's reference image.

Only VisualAsset.is_canonical_reference is managed here. is_current's
general current-vs-superseded semantics for a (entity, asset_type) pair
belong to 23D-L (Asset Versioning), not yet built — this subphase does
not depend on it and does not touch it.
"""
from sqlalchemy.orm import Session

from app.db.models.visual_asset import VisualAsset


class NPCReferenceError(ValueError):
    pass


def get_canonical_reference(
    db: Session, campaign_id: str | None, npc_id: str
) -> VisualAsset | None:
    """The NPC's current identity-anchor image, or None if it has never
    had one established yet."""
    return (
        db.query(VisualAsset)
        .filter(
            VisualAsset.campaign_id == campaign_id,
            VisualAsset.entity_type == "npc",
            VisualAsset.entity_id == npc_id,
            VisualAsset.is_canonical_reference.is_(True),
        )
        .order_by(VisualAsset.created_at.desc())
        .first()
    )


def set_canonical_reference(
    db: Session, campaign_id: str | None, npc_id: str, asset_id: str
) -> VisualAsset:
    """Designate `asset_id` as the NPC's new canonical identity-anchor
    reference (e.g. a fresh reference after in-world aging). Demotes
    whichever asset was previously canonical for this NPC — at most one
    is_canonical_reference=True row exists per NPC at a time, never
    overwritten in place, only superseded."""
    asset = db.get(VisualAsset, asset_id)
    if asset is None:
        raise NPCReferenceError(f"No VisualAsset with id {asset_id!r}.")
    if asset.entity_type != "npc" or asset.entity_id != npc_id:
        raise NPCReferenceError(f"Asset {asset_id!r} does not belong to NPC {npc_id!r}.")
    if asset.campaign_id != campaign_id:
        raise NPCReferenceError(f"Asset {asset_id!r} does not belong to campaign {campaign_id!r}.")

    previous = get_canonical_reference(db, campaign_id, npc_id)
    if previous is not None and previous.id != asset.id:
        previous.is_canonical_reference = False

    asset.is_canonical_reference = True
    db.flush()
    return asset


def get_current_portrait(
    db: Session, campaign_id: str | None, npc_id: str
) -> VisualAsset | None:
    """Whatever NPC_PORTRAIT asset is presently shown to the player —
    the most recently created is_current one, distinct from the
    canonical identity-anchor reference above."""
    return (
        db.query(VisualAsset)
        .filter(
            VisualAsset.campaign_id == campaign_id,
            VisualAsset.entity_type == "npc",
            VisualAsset.entity_id == npc_id,
            VisualAsset.asset_type == "NPC_PORTRAIT",
            VisualAsset.is_current.is_(True),
        )
        .order_by(VisualAsset.created_at.desc())
        .first()
    )
