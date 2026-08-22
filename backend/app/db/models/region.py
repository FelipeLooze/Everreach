from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DiscoveryStatus
from app.core.ids import generate_id
from app.db.base import Base


class Region(Base):
    """A large, self-contained part of the world. Created progressively, never all at once."""

    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("region"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")

    discovery_status: Mapped[str] = mapped_column(String, default=DiscoveryStatus.DISCOVERED)

    # Phase 15A — generation identity. generation_seed is derived from the
    # owning Campaign's world_seed (see app.game.world.generation.derive_seed),
    # never independently random, so the same campaign always reproduces the
    # same region. generation_version records which generator logic produced
    # this region so a future generator rewrite never silently regenerates
    # already-persisted worlds (see CURRENT_REGION_GENERATION_VERSION).
    generation_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    # Phase 15B — macro identity, generated from generation_seed alongside
    # (never instead of) the hand-authored `description` above.
    climate_summary: Mapped[str] = mapped_column(String, default="")
    cultural_summary: Mapped[str] = mapped_column(String, default="")
    historical_summary: Mapped[str] = mapped_column(String, default="")

    # Phase 15C — "WORLD MAP FIRST, ROOM DETAILS LATER": explicit gate so
    # deep materialization (15N+) can assert the macro skeleton (currently:
    # subregions) already exists before it ever runs.
    skeleton_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
