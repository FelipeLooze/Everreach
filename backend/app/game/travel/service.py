from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus, EventType
from app.db.models.location import Location, LocationConnection
from app.game.discovery.service import (
    get_connection_discovery,
    get_location_discovery,
    set_location_discovery,
)
from app.services.event_log import log_event


BASE_MINUTES_PER_DISTANCE = 15
DEFAULT_TRAVEL_SPEED_MULTIPLIER = 1.0

class TravelError(ValueError):
    pass

def calculate_travel_minutes(
    connection: LocationConnection,
    speed_multiplier: float = DEFAULT_TRAVEL_SPEED_MULTIPLIER,
) -> int:
    """Calculate deterministic travel time for one physical route.

    distance:
        Physical length of the route.

    travel_time_modifier:
        Difficulty of traversing the route itself.
        Values above 1.0 make travel slower.
        Values below 1.0 make travel faster.

    speed_multiplier:
        How fast the traveler is currently moving.
        1.0 means normal walking speed.
        Values above 1.0 are faster.
        Values below 1.0 are slower.
    """

    if speed_multiplier <= 0:
        raise TravelError(
            "O multiplicador de velocidade deve ser maior que zero."
        )

    raw_minutes = (
        BASE_MINUTES_PER_DISTANCE
        * connection.distance
        * connection.travel_time_modifier
        / speed_multiplier
    )

    return max(1, round(raw_minutes))

def find_connection(
    db: Session,
    from_location_id: str,
    to_location_id: str,
) -> LocationConnection | None:
    return (
        db.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == from_location_id,
            LocationConnection.to_location_id == to_location_id,
            LocationConnection.active.is_(True),
        )
        .first()
    )


def move_character(
    db: Session,
    campaign_id: str,
    character,
    to_location_id: str,
    speed_multiplier: float = DEFAULT_TRAVEL_SPEED_MULTIPLIER,
) -> int:
    """Move a character to a connected and known location.

    Returns minutes spent traveling.

    Raises TravelError when:
    - there is no active physical connection;
    - the character does not know that connection;
    - the destination does not exist.
    """

    from_location_id = character.location_id

    connection = find_connection(
        db,
        from_location_id,
        to_location_id,
    )

    if connection is None:
        raise TravelError(
            "Nenhum caminho liga a localização atual a esse destino."
        )

    connection_discovery = get_connection_discovery(
        db,
        character.id,
        connection.id,
    )

    if connection_discovery is None:
        raise TravelError(
            "Você conhece o destino, mas não conhece uma rota utilizável até ele."
        )

    destination = db.get(
        Location,
        to_location_id,
    )

    if destination is None:
        raise TravelError(
            "Destino desconhecido."
        )

    minutes = calculate_travel_minutes(
        connection,
        speed_multiplier,
    )

    previous_discovery = get_location_discovery(
        db,
        character.id,
        destination.id,
    )

    previous_status = (
        DiscoveryStatus(previous_discovery.status)
        if previous_discovery is not None
        else None
    )

    newly_discovered = (
        previous_status is None
        or previous_status == DiscoveryStatus.RUMORED
    )

    first_visit = (
        previous_status is None
        or previous_status
        in (
            DiscoveryStatus.RUMORED,
            DiscoveryStatus.DISCOVERED,
        )
    )

    # Move o personagem.
    character.location_id = destination.id
    character.region_id = destination.region_id

    # Marca o destino como visitado apenas para este personagem.
    set_location_discovery(
        db,
        character.id,
        destination.id,
        DiscoveryStatus.VISITED,
    )

    # Toda viagem realizada gera PLAYER_MOVED.
    log_event(
        db,
        campaign_id,
        EventType.PLAYER_MOVED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "from_location_id": from_location_id,
            "to_location_id": destination.id,
            "minutes": minutes,
        },
    )

    # Caso excepcional: chegou a um lugar que ainda não estava realmente descoberto.
    if newly_discovered:
        log_event(
            db,
            campaign_id,
            EventType.LOCATION_DISCOVERED,
            actor_type="character",
            actor_id=character.id,
            payload={
                "location_id": destination.id,
                "source": "travel",
            },
        )

    # Primeira vez que o personagem entra fisicamente neste lugar.
    if first_visit:
        log_event(
            db,
            campaign_id,
            EventType.LOCATION_VISITED,
            actor_type="character",
            actor_id=character.id,
            payload={
                "location_id": destination.id,
                "from_location_id": from_location_id,
            },
        )

    return minutes