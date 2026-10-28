from sqlalchemy import BigInteger, ForeignKey, ForeignKeyConstraint, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class GenesisPracticalHydrology(Base):
    __tablename__ = "genesis_practical_hydrology"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_water_reconciliations.campaign_id"), primary_key=True)
    practical_version: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    source_signature: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)


class GenesisLocalWaterAccount(Base):
    __tablename__ = "genesis_local_water_accounts"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_practical_hydrology.campaign_id"), primary_key=True)
    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    node: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[dict] = mapped_column(JSON, nullable=False)
    origin_checksum: Mapped[str] = mapped_column(String, nullable=False)
    balance: Mapped[dict] = mapped_column(JSON, nullable=False)
    state_checksum: Mapped[str] = mapped_column(String, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    head_id: Mapped[str] = mapped_column(String, nullable=False)
    last_minute: Mapped[int] = mapped_column(BigInteger, nullable=False)


class GenesisPracticalCapacityUse(Base):
    __tablename__ = "genesis_practical_capacity_use"
    __table_args__ = (ForeignKeyConstraint(["campaign_id", "revision_id"],
        ["genesis_water_revisions.campaign_id", "genesis_water_revisions.revision_id"]),)
    campaign_id: Mapped[str] = mapped_column(String, primary_key=True)
    capacity_key: Mapped[str] = mapped_column(String, primary_key=True)
    revision_id: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
