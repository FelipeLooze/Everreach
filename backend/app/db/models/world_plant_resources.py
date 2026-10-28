from sqlalchemy import ForeignKey,JSON,String
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class GenesisPlantResources(Base):
    __tablename__="genesis_plant_resources"
    campaign_id: Mapped[str]=mapped_column(ForeignKey("genesis_vegetation_plans.campaign_id"),primary_key=True)
    signature: Mapped[str]=mapped_column(String,nullable=False)
    descriptor: Mapped[dict]=mapped_column(JSON,nullable=False)
    descriptor_checksum: Mapped[str]=mapped_column(String,nullable=False)
