from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class BoundaryBarrier(Base):
    """
    Phase 16C — one concrete thing that makes a RegionalBoundary hard to
    cross. A boundary may have several (GEOGRAPHICAL + CLIMATIC +
    ECOLOGICAL etc. all at once, spec's "COMBINED BARRIERS") — never a
    single difficulty number. Each barrier is flavor + category only;
    what a character can actually do about one (16F feasibility, 16G
    hidden routes) reads this table, it doesn't live on it.
    """

    __tablename__ = "boundary_barriers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("barrier"))

    boundary_id: Mapped[str] = mapped_column(ForeignKey("regional_boundaries.id"), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
