from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.campaign import Campaign
from app.game.map.service import known_map
from app.schemas.map import MapConnection, MapLocation, MapRegion, MapResponse

router = APIRouter(prefix="/api/campaigns", tags=["map"])


@router.get("/{campaign_id}/map", response_model=MapResponse)
def get_map(campaign_id: str, db: Session = Depends(get_db)):
    if db.get(Campaign, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    data = known_map(db, campaign_id)
    return MapResponse(
        regions=[
            MapRegion(
                id=r.id, name=r.name, description=r.description, discovery_status=r.discovery_status,
                main_boss_name=r.main_boss_name, main_boss_location=r.main_boss_location,
                main_boss_requirements=r.main_boss_requirements,
            )
            for r in data["regions"]
        ],
        locations=[
            MapLocation(
                id=loc.id, region_id=loc.region_id, name=loc.name, type=loc.type,
                x=loc.x, y=loc.y, discovery_status=loc.discovery_status,
            )
            for loc in data["locations"]
        ],
        connections=[
            MapConnection(
                from_location_id=c.from_location_id, to_location_id=c.to_location_id,
                connection_type=c.connection_type, distance=c.distance, danger=c.danger,
            )
            for c in data["connections"]
        ],
    )
