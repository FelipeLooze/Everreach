from sqlalchemy import ForeignKey, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class GenesisRegionalGeology(Base):
    __tablename__ = "genesis_regional_geology"
    campaign_id: Mapped[str] = mapped_column(String,ForeignKey("genesis_geology_plans.campaign_id"),primary_key=True)
    regional_version: Mapped[int] = mapped_column(Integer,nullable=False)
    signature: Mapped[str] = mapped_column(String,nullable=False)
    descriptor: Mapped[dict] = mapped_column(JSON,nullable=False)
    policy: Mapped[dict] = mapped_column(JSON,nullable=False)
    policy_signature: Mapped[str] = mapped_column(String,nullable=False)
    source_checksum: Mapped[str] = mapped_column(String,nullable=False)
    write_epoch: Mapped[int] = mapped_column(Integer,nullable=False,default=0)


class GenesisRegionalFormation(Base):
    __tablename__ = "genesis_regional_formations"
    __table_args__ = (ForeignKeyConstraint(["campaign_id","parent_unit_id"],
        ["genesis_geological_units.campaign_id","genesis_geological_units.unit_id"]),)
    campaign_id: Mapped[str] = mapped_column(String,ForeignKey("genesis_regional_geology.campaign_id"),primary_key=True)
    formation_id: Mapped[str] = mapped_column(String,primary_key=True)
    parent_unit_id: Mapped[str] = mapped_column(String,nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON,nullable=False)
    baseline_checksum: Mapped[str] = mapped_column(String,nullable=False)
    changes: Mapped[dict] = mapped_column(JSON,nullable=False,default=dict)


class GenesisRegionalSource(Base):
    __tablename__ = "genesis_regional_sources"
    __table_args__ = (ForeignKeyConstraint(["campaign_id","formation_id"],
        ["genesis_regional_formations.campaign_id","genesis_regional_formations.formation_id"]),
        ForeignKeyConstraint(["campaign_id","deposit_id"],["genesis_mineral_deposits.campaign_id","genesis_mineral_deposits.deposit_id"]),
        UniqueConstraint("campaign_id","formation_id","material_id",name="uq_jr1_formation_material"))
    campaign_id: Mapped[str] = mapped_column(String,primary_key=True)
    deposit_id: Mapped[str] = mapped_column(String,primary_key=True)
    formation_id: Mapped[str] = mapped_column(String,nullable=False)
    material_id: Mapped[str] = mapped_column(String,nullable=False)
