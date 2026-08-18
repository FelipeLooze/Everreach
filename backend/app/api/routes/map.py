from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.campaign import Campaign
from app.game.map.service import known_map
from app.schemas.map import MapConnection, MapLocation, MapRegion, MapResponse
from app.core.enums import DiscoveryStatus, KnowerType
from app.db.models.character import Character
from app.game.knowledge.service import explicitly_knows_name

router = APIRouter(prefix="/api/campaigns", tags=["map"])

@router.get("/{campaign_id}/map", response_model=MapResponse)
def get_map(
    campaign_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    if db.get(Campaign, campaign_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Campanha não encontrada",
        )

    character = db.get(Character, character_id)

    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(
            status_code=404,
            detail="Personagem não encontrado nesta campanha",
        )

    data = known_map(
        db,
        campaign_id,
        character_id,
    )

    known_location_names = {
        loc.id: explicitly_knows_name(
            db,
            campaign_id,
            KnowerType.PLAYER,
            character.id,
            loc.name,
        )
        for loc in data["locations"]
    }

    known_region_names = {
        region.id: explicitly_knows_name(
            db,
            campaign_id,
            KnowerType.PLAYER,
            character.id,
            region.name,
        )
        for region in data["regions"]
    }

    locations = []

    for loc in data["locations"]:
        status = DiscoveryStatus(
            data["location_discovery"][loc.id]
        )

        coordinates_known = status in (
            DiscoveryStatus.DISCOVERED,
            DiscoveryStatus.VISITED,
            DiscoveryStatus.MAPPED,
        )

        locations.append(
            MapLocation(
                id=loc.id,
                region_id=loc.region_id,
                name=loc.name if known_location_names[loc.id] else None,
                type=loc.type,
                x=loc.x if coordinates_known else None,
                y=loc.y if coordinates_known else None,
                discovery_status=status.value,
            )
        )

    return MapResponse(
        regions=[
            MapRegion(
                id=region.id,
                name=(
                    region.name
                    if known_region_names[region.id]
                    else None
                ),
                description=None,
                discovery_status=region.discovery_status,
            )
            for region in data["regions"]
        ],
        locations=locations,
        connections=[
            MapConnection(
                from_location_id=connection.from_location_id,
                to_location_id=connection.to_location_id,
                direction=connection.direction,
                connection_type=connection.connection_type,
                distance=connection.distance,
                danger=connection.danger,
                travel_time_modifier=connection.travel_time_modifier,
            )
            for connection in data["connections"]
        ],
    )