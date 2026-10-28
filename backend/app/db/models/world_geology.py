from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class GenesisGeologyPlan(Base):
    __tablename__ = "genesis_geology_plans"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_terrain_plans.campaign_id"), primary_key=True)
    geology_version: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False, deferred=True)
    baseline_checksum: Mapped[str] = mapped_column(String, nullable=False)


class GenesisGeologicalUnit(Base):
    __tablename__ = "genesis_geological_units"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_geology_plans.campaign_id"), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String, primary_key=True)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False)
    baseline_checksum: Mapped[str] = mapped_column(String, nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class GenesisMineralDeposit(Base):
    __tablename__ = "genesis_mineral_deposits"
    __table_args__ = (ForeignKeyConstraint(["campaign_id", "unit_id"],
        ["genesis_geological_units.campaign_id", "genesis_geological_units.unit_id"]),
        CheckConstraint("remaining_units >= 0", name="ck_geology_finite_remaining"))
    campaign_id: Mapped[str] = mapped_column(String, primary_key=True)
    deposit_id: Mapped[str] = mapped_column(String, primary_key=True)
    unit_id: Mapped[str] = mapped_column(String, nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False)
    baseline_checksum: Mapped[str] = mapped_column(String, nullable=False)
    remaining_units: Mapped[int] = mapped_column(Integer, nullable=False)
