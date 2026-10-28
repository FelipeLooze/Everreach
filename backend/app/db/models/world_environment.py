from sqlalchemy import ForeignKey,ForeignKeyConstraint,Integer,JSON,String
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class GenesisEnvironmentPlan(Base):
    __tablename__="genesis_environment_plans"
    campaign_id: Mapped[str]=mapped_column(String,ForeignKey("genesis_regional_geology.campaign_id"),primary_key=True)
    environment_version: Mapped[int]=mapped_column(Integer,nullable=False)
    signature: Mapped[str]=mapped_column(String,nullable=False)
    descriptor: Mapped[dict]=mapped_column(JSON,nullable=False)
    descriptor_checksum: Mapped[str]=mapped_column(String,nullable=False)
    write_epoch: Mapped[int]=mapped_column(Integer,nullable=False,default=0)


class GenesisEnvironmentPoint(Base):
    __tablename__="genesis_environment_points"
    __table_args__=(ForeignKeyConstraint(["campaign_id","formation_id"],
        ["genesis_regional_formations.campaign_id","genesis_regional_formations.formation_id"]),)
    campaign_id: Mapped[str]=mapped_column(String,ForeignKey("genesis_environment_plans.campaign_id"),primary_key=True)
    probe_id: Mapped[str]=mapped_column(String,primary_key=True)
    formation_id: Mapped[str]=mapped_column(String,nullable=False)
    point: Mapped[list]=mapped_column(JSON,nullable=False)
    baseline: Mapped[dict]=mapped_column(JSON,nullable=False,deferred=True)
    baseline_checksum: Mapped[str]=mapped_column(String,nullable=False)
    changes: Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
