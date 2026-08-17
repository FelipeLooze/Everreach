from sqlalchemy.orm import Session

from app.db.models.region import Region


def get_region(db: Session, region_id: str) -> Region | None:
    return db.get(Region, region_id)


def list_regions(db: Session, campaign_id: str) -> list[Region]:
    return db.query(Region).filter(Region.campaign_id == campaign_id).all()
