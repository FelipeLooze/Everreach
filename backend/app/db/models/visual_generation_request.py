from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import VisualGenerationRequestStatus
from app.core.ids import generate_id
from app.db.base import Base


class VisualGenerationRequest(Base):
    """Phase 23D-D — Visual Generation Request.

    "REQUEST IS NOT ASSET" (spec, mandatory): this row records an
    ATTEMPT to materialize a visual asset through ComfyUI. It is never
    itself the generated image, and its existence or status never
    implies Canon changed. A COMPLETED request links to the VisualAsset
    it produced (23D-E, not yet built) via result_asset_id; a FAILED one
    keeps its error_code/error_message so a caller can show why, retry,
    or give up — gameplay must proceed exactly as if this row did not
    exist ("COMFYUI FAILURE != GAMEPLAY FAILURE", spec).

    entity_type/entity_id/asset_type reuse app.game.visual's existing
    addressing vocabulary rather than inventing a second one:
    entity_type values are app.game.visual.registry.VISUAL_SUBJECT_KINDS
    keys, asset_type values are app.game.visual.spec.FUTURE_ASSET_KINDS.
    workflow_key/workflow_version identify exactly which trusted graph
    (app.game.visual.workflow_registry) produced or will produce it.

    result_asset_id is deliberately a plain opaque string, not a
    ForeignKey: the visual_assets table (23D-E) does not exist yet, and
    when it does, VisualAsset ids will be generated the same way every
    other id in this codebase is (app.core.ids.generate_id) — there is
    no ambiguity to resolve later, just a table that has not been built
    yet in this deliberately sequenced phase.
    """

    __tablename__ = "visual_generation_requests"
    __table_args__ = (
        Index(
            "ix_visual_generation_request_dedup",
            "campaign_id", "entity_type", "entity_id", "asset_type", "status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("vgen"))

    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)

    workflow_key: Mapped[str] = mapped_column(String, nullable=False)
    workflow_version: Mapped[str] = mapped_column(String, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=VisualGenerationRequestStatus.PENDING,
        server_default=VisualGenerationRequestStatus.PENDING,
    )

    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    result_asset_id: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
