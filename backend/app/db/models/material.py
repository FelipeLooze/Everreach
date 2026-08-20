from sqlalchemy import CheckConstraint, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class MaterialDefinition(Base):
    """Broad physical characteristics consumed by weight and structural wear."""

    __tablename__ = "material_definitions"
    __table_args__ = (
        CheckConstraint("weight_factor > 0", name="ck_material_weight_factor_positive"),
        CheckConstraint(
            "wear_resistance > 0", name="ck_material_wear_resistance_positive"
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("material"),
    )
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, default="", nullable=False)
    weight_factor: Mapped[float] = mapped_column(Float, nullable=False)
    wear_resistance: Mapped[float] = mapped_column(Float, nullable=False)
