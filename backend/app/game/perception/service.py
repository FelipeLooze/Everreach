from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus, EventType, KnowerType, connection_type_label_pt
from app.services.event_log import log_event
from app.db.models.character import Character
from app.db.models.location import (
    Location,
    LocationConnection,
    LocationFeature,
)
from app.game.discovery.service import (
    discover_connection,
    set_location_discovery,
)
from app.game.npcs.service import known_facts


def _explicit_name_known(facts, name: str | None) -> bool:
    """Same check context_builder._explicit_name_known makes for the
    player-facing "CONNECTED LOCATIONS KNOWN TO PLAYER" section —
    duplicated locally rather than imported across the game/ai layer
    boundary. observe_surroundings' own route text previously revealed
    a destination's canonical name unconditionally, with no equivalent
    gate at all (confirmed via live trace as a real regression: "PATH
    para Estalagem de Morven" was fed to the narrator as an AUTHORITATIVE
    MECHANICAL FACT before the player had ever learned the settlement's
    name), while the parallel context_builder section already redacted
    it to "Local desconhecido" — this closes that gap at the source."""
    if not name:
        return False
    normalized_name = name.casefold()
    return any(normalized_name in fact.statement.casefold() for fact in facts)


@dataclass
class PerceptionResult:
    location_name: str
    location_name_known: bool = True
    features: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    discovered_locations: list[str] = field(default_factory=list)
    discovered_connections: list[str] = field(default_factory=list)


def observe_surroundings(
    db: Session,
    character: Character,
) -> PerceptionResult:
    if character.location_id is None:
        raise ValueError("O personagem não possui localização atual.")

    location = db.get(Location, character.location_id)

    if location is None:
        raise ValueError("Localização atual não encontrada.")

    features = (
        db.query(LocationFeature)
        .filter(
            LocationFeature.location_id == location.id,
            LocationFeature.visible.is_(True),
        )
        .order_by(LocationFeature.name)
        .all()
    )

    connections = (
        db.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == location.id,
            LocationConnection.active.is_(True),
        )
        .all()
    )

    player_facts = known_facts(db, character.campaign_id, KnowerType.PLAYER, character.id)

    result = PerceptionResult(
        location_name=location.name,
        location_name_known=_explicit_name_known(player_facts, location.name),
        features=[
            f"{feature.name}: {feature.description}"
            for feature in features
        ],
    )

    for connection in connections:
        destination = db.get(Location, connection.to_location_id)

        if destination is None:
            continue

        _connection_discovery, connection_changed = discover_connection(
            db,
            character.id,
            connection.id,
        )

        _location_discovery, location_changed = set_location_discovery(
            db,
            character.id,
            destination.id,
            DiscoveryStatus.DISCOVERED,
        )

        direction = connection.direction or "direção não registrada"
        destination_label = (
            destination.name
            if _explicit_name_known(player_facts, destination.name)
            else "um local desconhecido"
        )

        result.routes.append(
            f"{direction}: {connection_type_label_pt(connection.connection_type)} para "
            f"{destination_label} (distância {connection.distance:g})"
        )

        if connection_changed:
            result.discovered_connections.append(connection.id)

            log_event(
                db,
                character.campaign_id,
                EventType.CONNECTION_DISCOVERED,
                actor_type="character",
                actor_id=character.id,
                payload={
                    "connection_id": connection.id,
                    "from_location_id": connection.from_location_id,
                    "to_location_id": connection.to_location_id,
                    "direction": connection.direction,
                    "connection_type": connection.connection_type,
                    "source": "observation",
                },
            )

        if location_changed:
            result.discovered_locations.append(destination.name)

            log_event(
                db,
                character.campaign_id,
                EventType.LOCATION_DISCOVERED,
                actor_type="character",
                actor_id=character.id,
                payload={
                    "location_id": destination.id,
                    "source": "observation",
                },
            )

    return result