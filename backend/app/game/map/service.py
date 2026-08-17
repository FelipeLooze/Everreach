from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus
from app.db.models.location import (
    CharacterLocationDiscovery,
    Location,
    LocationConnection,
)
from app.db.models.region import Region


def known_map(
    db: Session,
    campaign_id: str,
    character_id: str,
) -> dict:
    """Return only the part of the world known by one character.

    Absence of CharacterLocationDiscovery means UNKNOWN.

    RUMORED locations are included, but their exact coordinates should not
    necessarily be exposed by the API.
    """

    location_rows = (
        db.query(Location, CharacterLocationDiscovery)
        .join(
            CharacterLocationDiscovery,
            CharacterLocationDiscovery.location_id == Location.id,
        )
        .join(
            Region,
            Region.id == Location.region_id,
        )
        .filter(
            Region.campaign_id == campaign_id,
            CharacterLocationDiscovery.character_id == character_id,
            CharacterLocationDiscovery.status != DiscoveryStatus.UNKNOWN,
        )
        .order_by(Location.name)
        .all()
    )

    if not location_rows:
        return {
            "regions": [],
            "locations": [],
            "location_discovery": {},
            "connections": [],
        }

    locations = [location for location, _discovery in location_rows]

    location_discovery = {
        location.id: discovery.status
        for location, discovery in location_rows
    }

    location_ids = {location.id for location in locations}
    region_ids = {location.region_id for location in locations}

    regions = (
        db.query(Region)
        .filter(
            Region.campaign_id == campaign_id,
            Region.id.in_(region_ids),
        )
        .order_by(Region.name)
        .all()
    )

    connections = (
        db.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id.in_(location_ids),
            LocationConnection.to_location_id.in_(location_ids),
            LocationConnection.active.is_(True),
        )
        .all()
    )

    return {
        "regions": regions,
        "locations": locations,
        "location_discovery": location_discovery,
        "connections": connections,
    }