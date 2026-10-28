from sqlalchemy import ForeignKey,ForeignKeyConstraint,JSON,String,Integer
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class GenesisVegetationPlan(Base):
    __tablename__="genesis_vegetation_plans"
    campaign_id: Mapped[str]=mapped_column(ForeignKey("genesis_environment_plans.campaign_id"),primary_key=True)
    signature: Mapped[str]=mapped_column(String,nullable=False)
    descriptor: Mapped[dict]=mapped_column(JSON,nullable=False)
    descriptor_checksum: Mapped[str]=mapped_column(String,nullable=False)
    write_epoch: Mapped[int]=mapped_column(Integer,default=0,nullable=False)


class GenesisVegetationCommunity(Base):
    __tablename__="genesis_vegetation_communities"
    campaign_id: Mapped[str]=mapped_column(ForeignKey("genesis_vegetation_plans.campaign_id"),primary_key=True)
    community_id: Mapped[str]=mapped_column(String,primary_key=True)
    baseline: Mapped[dict]=mapped_column(JSON,nullable=False,deferred=True)
    baseline_checksum: Mapped[str]=mapped_column(String,nullable=False)


class GenesisPlantIndividual(Base):
    __tablename__="genesis_plant_individuals"
    __table_args__=(ForeignKeyConstraint(["campaign_id","community_id"],
        ["genesis_vegetation_communities.campaign_id","genesis_vegetation_communities.community_id"]),)
    campaign_id: Mapped[str]=mapped_column(String,primary_key=True)
    individual_id: Mapped[str]=mapped_column(String,primary_key=True)
    community_id: Mapped[str]=mapped_column(String,index=True,nullable=False)
    baseline: Mapped[dict]=mapped_column(JSON,nullable=False)
    baseline_checksum: Mapped[str]=mapped_column(String,nullable=False)
    state: Mapped[dict]=mapped_column(JSON,nullable=False)
    state_checksum: Mapped[str]=mapped_column(String,nullable=False)


class GenesisPlantAction(Base):
    __tablename__="genesis_plant_actions"
    __table_args__=(ForeignKeyConstraint(["campaign_id","individual_id"],
        ["genesis_plant_individuals.campaign_id","genesis_plant_individuals.individual_id"]),)
    campaign_id: Mapped[str]=mapped_column(String,primary_key=True)
    action_id: Mapped[str]=mapped_column(String,primary_key=True)
    individual_id: Mapped[str]=mapped_column(String,nullable=False)
    actor_id: Mapped[str]=mapped_column(ForeignKey("characters.id"),nullable=False)
    receipt: Mapped[dict]=mapped_column(JSON,nullable=False)
    receipt_checksum: Mapped[str]=mapped_column(String,nullable=False)


class GenesisBotanicalToolCertificate(Base):
    """Fine operations are not implied by a named tool or coarse CUTTING capability."""
    __tablename__="genesis_botanical_tool_certificates"
    item_id: Mapped[str]=mapped_column(ForeignKey("item_tool_profiles.item_id"),primary_key=True)
    certificate: Mapped[dict]=mapped_column(JSON,nullable=False)
    certificate_checksum: Mapped[str]=mapped_column(String,nullable=False)
