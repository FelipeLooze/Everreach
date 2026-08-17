from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus, EventType
from app.db.models.location import Location, LocationConnection
from app.services.event_log import log_event

BASE_MINUTES_PER_DISTANCE = 15


class TravelError(ValueError):
    pass


def find_connection(db: Session, from_location_id: str, to_location_id: str) -> LocationConnection | None:
    return (
        db.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == from_location_id,
            LocationConnection.to_location_id == to_location_id,
            LocationConnection.active.is_(True),
        )
        .first()
    )


def move_character(db: Session, campaign_id: str, character, to_location_id: str) -> int:
    """Move a character to a connected location. Returns minutes spent traveling.
    Raises TravelError if there is no active connection — movement is never free-form."""
    connection = find_connection(db, character.location_id, to_location_id)
    if connection is None:
        raise TravelError("Nenhum caminho conhecido liga a localização atual a esse destino.")

    destination = db.get(Location, to_location_id)
    if destination is None:
        raise TravelError("Destino desconhecido.")

    minutes = round(BASE_MINUTES_PER_DISTANCE * connection.distance * connection.travel_time_modifier)

    character.location_id = destination.id
    character.region_id = destination.region_id

    newly_discovered = destination.discovery_status == DiscoveryStatus.UNKNOWN
    if destination.discovery_status in (DiscoveryStatus.UNKNOWN, DiscoveryStatus.RUMORED, DiscoveryStatus.DISCOVERED):
        destination.discovery_status = DiscoveryStatus.VISITED

    log_event(
        db,
        campaign_id,
        EventType.PLAYER_MOVED,
        actor_type="character",
        actor_id=character.id,
        payload={"to_location_id": to_location_id, "minutes": minutes},
    )
    if newly_discovered:
        log_event(
            db,
            campaign_id,
            EventType.LOCATION_DISCOVERED,
            actor_type="character",
            actor_id=character.id,
            payload={"location_id": to_location_id},
        )

    return minutes
