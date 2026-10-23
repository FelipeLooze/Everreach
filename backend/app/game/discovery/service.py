from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus
from app.db.models.location import CharacterLocationDiscovery, CharacterConnectionDiscovery, Location
from app.core.logging import get_logger


logger = get_logger("game")


_DISCOVERY_RANK = {
    DiscoveryStatus.DISCOVERED: 1,
    DiscoveryStatus.VISITED: 2,
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

    Discovery is monotonic: DISCOVERED -> VISITED.

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


def record_location_visit(
    db: Session,
    character_id: str,
    location_id: str,
    *,
    source: str,
) -> tuple[CharacterLocationDiscovery, bool]:
    """Record one authoritative physical arrival.

    ``visited_at`` remains the first visit for save compatibility;
    ``last_visited_at`` and ``visit_count`` describe subsequent arrivals.
    Knowledge or dialogue must never call this function.
    """
    before = get_location_discovery(db, character_id, location_id)
    was_visited = before is not None and before.status == DiscoveryStatus.VISITED
    discovery, _changed = set_location_discovery(
        db, character_id, location_id, DiscoveryStatus.VISITED
    )
    now = discovery.visited_at if not was_visited and discovery.visited_at is not None else _now()
    if discovery.visited_at is None:
        discovery.visited_at = now
    discovery.last_visited_at = now
    discovery.visit_count = max(0, discovery.visit_count or 0) + 1
    db.flush()
    logger.debug(
        "location visit character=%s location=%s source=%s first=%s count=%s",
        character_id,
        location_id,
        source,
        not was_visited,
        discovery.visit_count,
    )
    return discovery, not was_visited


def location_display_name(
    location: Location,
    discovery: CharacterLocationDiscovery | None,
    *,
    canonical_name_known: bool = False,
) -> str | None:
    """Common-case visited name with an explicit secret-identity exception."""
    if canonical_name_known:
        return location.name
    visited = discovery is not None and discovery.status == DiscoveryStatus.VISITED
    if not visited:
        return None
    if location.identity_hidden:
        return location.unrevealed_name
    return location.name
