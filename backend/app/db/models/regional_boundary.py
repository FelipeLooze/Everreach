from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class RegionalBoundary(Base):
    """
    Phase 16B — the world conditions separating two massive Regions.

    A Boundary is NOT a map line and NOT a level gate (spec's "REGION
    BORDER = WORLD PROBLEM"). It is deliberately lean: what makes crossing
    hard lives in BoundaryBarrier rows (16C, one or more per boundary,
    combinable categories) and what routes exist through it live in
    BoundaryRoute rows (16D) — "BOUNDARY != ROUTE" is a spec-level
    distinction, kept as two separate tables rather than folded into this
    one. No required_level/minimum_power/accessibility-state column
    exists here on purpose: feasibility is always derived (16F), never a
    stored gate, and accessibility can change over time (spec) without
    ever touching this row.

    destination_region_id stays NULL until a later subphase (16I+)
    actually materializes the neighboring Region — a Boundary may exist,
    fully described, long before its far side does (spec's "A Region may
    physically exist... while currently being extremely difficult to
    reach" applies just as much to "may not exist yet").
    """

    __tablename__ = "regional_boundaries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("bound"))

    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    source_region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), nullable=False)
    destination_region_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"), nullable=True)

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")

    # Which side of source_region this boundary sits on (e.g. "leste") —
    # free-text, matches the "Border side: East" constraint field the
    # 16H neighbor-generation package will carry, never a coordinate.
    boundary_side: Mapped[str] = mapped_column(String, default="")

    # The one anchor Subregion (in source_region) this boundary is
    # physically attached to, and the one real Location (also in
    # source_region) that represents "the edge, where this barrier
    # begins" — reachable through the ordinary travel graph like any
    # other Location, never a special-cased destination.
    anchor_subregion_id: Mapped[str] = mapped_column(ForeignKey("subregions.id"), nullable=False)
    frontier_location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)

    generation_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
