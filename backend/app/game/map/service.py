from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus
from app.db.models.location import Location, LocationConnection
from app.db.models.region import Region


def known_map(db: Session, campaign_id: str) -> dict:
    """Only regions/locations that are not UNKNOWN are exposed to the player —
    the world truth vs. player knowledge distinction from spec section 40."""
    regions = db.query(Region).filter(Region.campaign_id == campaign_id).all()
    region_ids = [r.id for r in regions]

    locations = (
        db.query(Location)
        .filter(Location.region_id.in_(region_ids), Location.discovery_status != DiscoveryStatus.UNKNOWN)
        .all()
    )
    location_ids = {loc.id for loc in locations}

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
        "connections": connections,
    }
