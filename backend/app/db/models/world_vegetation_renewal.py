from sqlalchemy import String,Integer,JSON,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class GenesisVegetationRenewal(Base):
    __tablename__='genesis_vegetation_renewal'
    campaign_id: Mapped[str]=mapped_column(String,ForeignKey('genesis_vegetation_life.campaign_id'),primary_key=True)
    signature: Mapped[str]=mapped_column(String,nullable=False)
    descriptor: Mapped[dict]=mapped_column(JSON,nullable=False)
    descriptor_checksum: Mapped[str]=mapped_column(String,nullable=False)
    last_minute: Mapped[int]=mapped_column(Integer,nullable=False)
    state_checksum: Mapped[str]=mapped_column(String,nullable=False)


class GenesisRenewingPopulation(Base):
    __tablename__='genesis_renewing_populations'
    campaign_id: Mapped[str]=mapped_column(String,ForeignKey('genesis_vegetation_renewal.campaign_id'),primary_key=True)
    population_id: Mapped[str]=mapped_column(String,primary_key=True)
    community_id: Mapped[str]=mapped_column(String,index=True,nullable=False)
    species_id: Mapped[str]=mapped_column(String,nullable=False)
    data: Mapped[dict]=mapped_column(JSON,nullable=False)
    data_checksum: Mapped[str]=mapped_column(String,nullable=False)
