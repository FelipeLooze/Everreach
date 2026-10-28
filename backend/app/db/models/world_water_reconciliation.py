from sqlalchemy import BigInteger, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class GenesisWaterReconciliation(Base):
    __tablename__ = "genesis_water_reconciliations"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_water_plans.campaign_id"),
        ForeignKey("genesis_hydro_geometry_plans.campaign_id"), primary_key=True)
    water_version: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    sources: Mapped[dict] = mapped_column(JSON, nullable=False)
    cutover_minute: Mapped[int] = mapped_column(BigInteger, nullable=False)
    write_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GenesisWaterDomain(Base):
    __tablename__ = "genesis_water_domains"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_water_reconciliations.campaign_id"), primary_key=True)
    node: Mapped[int] = mapped_column(Integer, primary_key=True)
    head_id: Mapped[str] = mapped_column(String, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_minute: Mapped[int] = mapped_column(BigInteger, nullable=False)
    opening_checksum: Mapped[str] = mapped_column(String, nullable=False)
    state_checksum: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[dict] = mapped_column(JSON, nullable=False)


class GenesisWaterReconciliationEvidence(Base):
    __tablename__ = "genesis_water_reconciliation_evidence"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_water_reconciliations.campaign_id"), primary_key=True)
    evidence_key: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    node: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String, nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False)


class GenesisWaterRevision(Base):
    __tablename__ = "genesis_water_revisions"
    __table_args__ = (UniqueConstraint("campaign_id", "operation_id", name="uq_w2_operation"),)
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_water_reconciliations.campaign_id"), primary_key=True)
    revision_id: Mapped[str] = mapped_column(String, primary_key=True)
    operation_id: Mapped[str] = mapped_column(String, nullable=False)
    request_checksum: Mapped[str] = mapped_column(String, nullable=False)
    payload_checksum: Mapped[str] = mapped_column(String, nullable=False)
    logical_minute: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, deferred=True)


class GenesisWaterTransfer(Base):
    __tablename__ = "genesis_water_transfers"
    __table_args__ = (ForeignKeyConstraint(["campaign_id", "revision_id"],
        ["genesis_water_revisions.campaign_id", "genesis_water_revisions.revision_id"]),)
    campaign_id: Mapped[str] = mapped_column(String, primary_key=True)
    transfer_id: Mapped[str] = mapped_column(String, primary_key=True)
    revision_id: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
