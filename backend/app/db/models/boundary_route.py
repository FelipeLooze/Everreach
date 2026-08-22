from sqlalchemy import Boolean, ForeignKey, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class BoundaryRoute(Base):
    """
    Phase 16D — one possible way through a RegionalBoundary. A boundary
    usually has 2-3 of these with genuinely different tradeoffs (spec's
    "NO SINGLE REQUIRED ROUTE"), never exactly one.

    "BOUNDARY != ROUTE": the boundary is the barrier itself (16B/16C);
    this table is only the possible methods of getting through it.

    origin_location_id is always real (the boundary's own frontier
    Location, 16B) — reachable through the ordinary travel graph today.
    destination_location_id stays NULL until the neighboring Region
    actually materializes and 16Q wires up the real LocationConnection
    pair; a route can be fully described, and even discoverable, long
    before that happens.
    """

    __tablename__ = "boundary_routes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("route"))

    boundary_id: Mapped[str] = mapped_column(ForeignKey("regional_boundaries.id"), nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    terrain: Mapped[str] = mapped_column(String, default="")

    origin_location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    destination_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

    # A rough estimate only — once 16Q creates the real LocationConnection
    # pair, that connection's own distance/danger become authoritative for
    # actual travel; these stay as the pre-crossing preview a character's
    # preparation (16F) reasons about.
    estimated_distance: Mapped[float] = mapped_column(Float, default=1.0)
    danger_hint: Mapped[int] = mapped_column(Integer, default=0)

    political_control: Mapped[str] = mapped_column(String, default="")

    # Phase 16E — the one season this route is roughest in (mountain
    # passes: WINTER; desert-like crossings: SUMMER heat; storm-prone
    # water routes: AUTUMN). Accessibility itself is never stored — see
    # app.game.world.boundaries.route_accessibility_for_season, which
    # derives OPEN/RISKY/NEARLY_IMPASSABLE from this plus the current
    # in-world season on demand.
    harsh_season: Mapped[str] = mapped_column(String, default="WINTER")

    # False means this route is not common knowledge — nobody is granted
    # the corresponding KnowledgeFact automatically (16G discovers these
    # through exploration/NPC knowledge/old maps, not by default).
    is_publicly_known: Mapped[bool] = mapped_column(Boolean, default=True)

    knowledge_fact_key: Mapped[str] = mapped_column(String, default="")
