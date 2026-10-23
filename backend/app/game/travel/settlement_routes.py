"""Walking between two buildings of the same settlement.

Settlement services only connect to the settlement's square (hub and
spokes), so going from the forge to the inn had no direct route and the
player was told no path existed. Here such a walk becomes two real legs —
building to square, square to building — each through move_character, so
discovery, time, stamina, incidents and events stay exactly as they are.
"""

from dataclasses import replace

from sqlalchemy.orm import Session

from app.core.enums import TravelPace
from app.db.models.location import Location
from app.game.discovery.service import get_connection_discovery
from app.game.travel.service import TravelResult, find_connection, move_character


def _square_between(db: Session, character_id: str, origin_id: str, destination_id: str) -> str | None:
    """The shared square, when both legs exist and both are known — never
    leave the character stranded at the square by a second leg that fails."""
    origin = db.get(Location, origin_id)
    destination = db.get(Location, destination_id)
    if origin is None or destination is None:
        return None
    square_id = origin.parent_location_id
    if square_id is None or square_id != destination.parent_location_id:
        return None
    legs = (find_connection(db, origin_id, square_id), find_connection(db, square_id, destination_id))
    if any(leg is None or get_connection_discovery(db, character_id, leg.id) is None for leg in legs):
        return None
    return square_id


def move_within_reach(
    db: Session,
    campaign_id: str,
    character,
    to_location_id: str,
    pace: TravelPace = TravelPace.NORMAL,
) -> TravelResult:
    """move_character, or two legs through the square for sibling buildings."""
    if find_connection(db, character.location_id, to_location_id) is None:
        square_id = _square_between(db, character.id, character.location_id, to_location_id)
        if square_id is not None:
            first = move_character(db, campaign_id, character, square_id, pace=pace)
            second = move_character(db, campaign_id, character, to_location_id, pace=pace)
            return replace(
                second,
                minutes=first.minutes + second.minutes,
                base_minutes=first.base_minutes + second.base_minutes,
                stamina_spent=first.stamina_spent + second.stamina_spent,
                incident=second.incident or first.incident,
            )
    return move_character(db, campaign_id, character, to_location_id, pace=pace)
