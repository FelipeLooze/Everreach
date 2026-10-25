"""Internal adapter for a future spherical map, using the existing knowledge view.

No API endpoint exposes authoritative anchors. Unknown/unvisited locations never
gain exact geometry through this adapter, including known regional coverage.
"""
from sqlalchemy.orm import Session

from app.core.enums import GeographicPrecision
from app.db.models.character import Character
from app.db.models.world_spatial import LocationSpatialAnchor
from app.game.map.view import get_map_view
from .spatial import sphere_world


def known_spatial_locations(db: Session, campaign_id: str, character_id: str, *,
                            scope: str | None = None) -> dict[str, list[int]]:
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to this campaign")
    sphere_world(db, campaign_id)
    view = get_map_view(db, campaign_id, character_id, scope=scope)
    precise_ids = [location.id for location in view.locations
                   if location.precision == GeographicPrecision.PRECISE.value]
    if not precise_ids:
        return {}
    anchors = db.query(LocationSpatialAnchor).filter(
        LocationSpatialAnchor.campaign_id == campaign_id,
        LocationSpatialAnchor.location_id.in_(precise_ids)).all()
    return {anchor.location_id: list(anchor.point) for anchor in anchors}
