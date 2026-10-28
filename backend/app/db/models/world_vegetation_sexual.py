from sqlalchemy import String,JSON,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class GenesisVegetationSexualPolicy(Base):
    __tablename__='genesis_vegetation_sexual_policy'
    campaign_id: Mapped[str]=mapped_column(String,ForeignKey('genesis_vegetation_renewal.campaign_id'),primary_key=True)
    signature: Mapped[str]=mapped_column(String,nullable=False)
    descriptor: Mapped[dict]=mapped_column(JSON,nullable=False)
    descriptor_checksum: Mapped[str]=mapped_column(String,nullable=False)
