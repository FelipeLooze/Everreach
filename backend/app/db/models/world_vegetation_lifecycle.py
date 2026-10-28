from sqlalchemy import ForeignKey,ForeignKeyConstraint,JSON,String,Integer,Index
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class GenesisVegetationLife(Base):
    __tablename__="genesis_vegetation_life"
    campaign_id: Mapped[str]=mapped_column(String,ForeignKey("genesis_plant_resources.campaign_id"),primary_key=True)
    signature: Mapped[str]=mapped_column(String,nullable=False)
    descriptor: Mapped[dict]=mapped_column(JSON,nullable=False)
    descriptor_checksum: Mapped[str]=mapped_column(String,nullable=False)
    write_epoch: Mapped[int]=mapped_column(Integer,nullable=False,default=0)


class GenesisLivingPopulation(Base):
    __tablename__="genesis_living_populations"
    campaign_id: Mapped[str]=mapped_column(String,ForeignKey("genesis_vegetation_life.campaign_id"),primary_key=True)
    population_id: Mapped[str]=mapped_column(String,primary_key=True)
    community_id: Mapped[str]=mapped_column(String,index=True,nullable=False)
    species_id: Mapped[str]=mapped_column(String,nullable=False)
    data: Mapped[dict]=mapped_column(JSON,nullable=False)
    data_checksum: Mapped[str]=mapped_column(String,nullable=False)


class GenesisVegetationLifeEvent(Base):
    __tablename__="genesis_vegetation_life_events"
    __table_args__=(Index("ix_life_event_due","campaign_id","population_id","status","due_minute"),)
    campaign_id: Mapped[str]=mapped_column(String,ForeignKey("genesis_vegetation_life.campaign_id"),primary_key=True)
    event_id: Mapped[str]=mapped_column(String,primary_key=True)
    population_id: Mapped[str]=mapped_column(String,nullable=False)
    due_minute: Mapped[int]=mapped_column(Integer,nullable=False)
    status: Mapped[str]=mapped_column(String,nullable=False)
    payload: Mapped[dict]=mapped_column(JSON,nullable=False)
    payload_checksum: Mapped[str]=mapped_column(String,nullable=False)
