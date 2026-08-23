from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import VisualAssetValidationStatus
from app.core.ids import generate_id
from app.db.base import Base


class VisualAsset(Base):
    """Phase 23D-E — a successfully materialized generated visual asset.

    "REQUEST IS NOT ASSET" (spec, mandatory): app.db.models.visual_
    generation_request.VisualGenerationRequest records an attempt; this
    table records a result. Only a COMPLETED request ever produces one
    of these rows (via its result_asset_id).

    entity_type/entity_id/asset_type reuse the same addressing
    vocabulary as VisualGenerationRequest and VisualIdentity (Phase 21C)
    — entity_type values are app.game.visual.registry.
    VISUAL_SUBJECT_KINDS keys, asset_type values are app.game.visual.
    spec.FUTURE_ASSET_KINDS. A later subphase links an entity's current
    asset back into VisualIdentity.asset_refs_json (Phase 21Q's own
    generic slot for exactly this) by storing this row's id there —
    this table itself never mutates VisualIdentity.

    storage_path is relative to comfyui_asset_root (never ComfyUI's own
    raw output directory — see 23D-F for the copy step that produces
    it), and is always ID-based, never derived from user-controlled
    text, so it can never traverse outside that root.

    is_current / validation_status only get their real state-transition
    behavior in later subphases (23D-L asset versioning, 23D-M
    validation review) — this subphase defines just the columns and
    their safe defaults: a newly materialized asset starts as the
    current one and UNREVIEWED.
    """

    __tablename__ = "visual_assets"
    __table_args__ = (
        Index(
            "ix_visual_asset_current",
            "campaign_id", "entity_type", "entity_id", "asset_type", "is_current",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("vasset"))

    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)

    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)

    workflow_key: Mapped[str] = mapped_column(String, nullable=False)
    workflow_version: Mapped[str] = mapped_column(String, nullable=False)
    model_identifier: Mapped[str] = mapped_column(String, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    validation_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=VisualAssetValidationStatus.UNREVIEWED,
        server_default=VisualAssetValidationStatus.UNREVIEWED,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    is_canonical_reference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
