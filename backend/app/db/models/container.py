from sqlalchemy import CheckConstraint, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ItemContainerProfile(Base):
    """Authoritative carrying capacity of a container definition."""

    __tablename__ = "item_container_profiles"
    __table_args__ = (
        CheckConstraint(
            "weight_capacity > 0",
            name="ck_item_container_weight_capacity_positive",
        ),
    )

    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id"),
        primary_key=True,
    )
    weight_capacity: Mapped[float] = mapped_column(Float, nullable=False)

    item: Mapped["ItemDefinition"] = relationship()
