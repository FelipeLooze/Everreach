from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus
from app.db.models.location import CharacterLocationDiscovery, CharacterConnectionDiscovery


_DISCOVERY_RANK = {
    DiscoveryStatus.RUMORED: 1,
    DiscoveryStatus.DISCOVERED: 2,
    DiscoveryStatus.VISITED: 3,
    DiscoveryStatus.MAPPED: 4,
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def get_location_discovery(
    db: Session,
    character_id: str,
    location_id: str,
) -> CharacterLocationDiscovery | None:
    return (
        db.query(CharacterLocationDiscovery)
        .filter(
            CharacterLocationDiscovery.character_id == character_id,
            CharacterLocationDiscovery.location_id == location_id,
        )
        .first()
    )


def set_location_discovery(
    db: Session,
    character_id: str,
    location_id: str,
    status: DiscoveryStatus | str,
) -> tuple[CharacterLocationDiscovery, bool]:
    """Create or advance one character's discovery state.

    Discovery is monotonic:
    RUMORED -> DISCOVERED -> VISITED -> MAPPED.

    UNKNOWN is represented by the absence of a database row.

    Returns:
        (discovery, changed)
    """

    target_status = DiscoveryStatus(status)

    if target_status == DiscoveryStatus.UNKNOWN:
        raise ValueError(
            "UNKNOWN is represented by the absence of a discovery record."
        )

    discovery = get_location_discovery(
        db,
        character_id,
        location_id,
    )

    now = _now()

    if discovery is None:
        discovery = CharacterLocationDiscovery(
            character_id=character_id,
            location_id=location_id,
            status=target_status,
        )

        if _DISCOVERY_RANK[target_status] >= _DISCOVERY_RANK[DiscoveryStatus.DISCOVERED]:
            discovery.discovered_at = now

        if _DISCOVERY_RANK[target_status] >= _DISCOVERY_RANK[DiscoveryStatus.VISITED]:
            discovery.visited_at = now

        if target_status == DiscoveryStatus.MAPPED:
            discovery.mapped_at = now

        db.add(discovery)
        db.flush()

        return discovery, True

    current_status = DiscoveryStatus(discovery.status)

    if _DISCOVERY_RANK[target_status] <= _DISCOVERY_RANK[current_status]:
        return discovery, False

    discovery.status = target_status

    if (
        discovery.discovered_at is None
        and _DISCOVERY_RANK[target_status]
        >= _DISCOVERY_RANK[DiscoveryStatus.DISCOVERED]
    ):
        discovery.discovered_at = now

    if (
        discovery.visited_at is None
        and _DISCOVERY_RANK[target_status]
        >= _DISCOVERY_RANK[DiscoveryStatus.VISITED]
    ):
        discovery.visited_at = now

    if (
        discovery.mapped_at is None
        and target_status == DiscoveryStatus.MAPPED
    ):
        discovery.mapped_at = now

    db.flush()

    return discovery, True

def get_connection_discovery(
    db: Session,
    character_id: str,
    connection_id: str,
) -> CharacterConnectionDiscovery | None:
    return (
        db.query(CharacterConnectionDiscovery)
        .filter(
            CharacterConnectionDiscovery.character_id == character_id,
            CharacterConnectionDiscovery.connection_id == connection_id,
        )
        .first()
    )


def discover_connection(
    db: Session,
    character_id: str,
    connection_id: str,
) -> tuple[CharacterConnectionDiscovery, bool]:
    existing = get_connection_discovery(
        db,
        character_id,
        connection_id,
    )

    if existing is not None:
        return existing, False

    discovery = CharacterConnectionDiscovery(
        character_id=character_id,
        connection_id=connection_id,
    )

    db.add(discovery)
    db.flush()

    return discovery, True