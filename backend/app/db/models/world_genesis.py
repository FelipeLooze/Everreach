from sqlalchemy import ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GenesisWorld(Base):
    __tablename__ = "genesis_worlds"

    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), primary_key=True)
    world_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)


class GenesisSector(Base):
    __tablename__ = "genesis_sectors"

    campaign_id: Mapped[str] = mapped_column(ForeignKey("genesis_worlds.campaign_id"), primary_key=True)
    x: Mapped[int] = mapped_column(Integer, primary_key=True)
    y: Mapped[int] = mapped_column(Integer, primary_key=True)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Simulation changes are separate from immutable generated geography.
    # Assign a new dictionary to persist updates (SQLAlchemy plain JSON).
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
