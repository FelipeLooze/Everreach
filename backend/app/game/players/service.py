import json
import random

from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    SimulatedPlayerStatus,
)
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.db.models.location import Location
from app.db.models.simulated_player import SimulatedPlayer
from app.services.event_log import log_event


_CONVERSATION_BOUNDARY_EVENTS = (
    EventType.PLAYER_MET_NPC.value,
    EventType.PLAYER_TALKED_TO_NPC.value,
    EventType.PLAYER_MET_SIMULATED_PLAYER.value,
    EventType.PLAYER_TALKED_TO_SIMULATED_PLAYER.value,
    EventType.PLAYER_MOVED.value,
    EventType.PLAYER_RESTED.value,
    EventType.PLAYER_DIED.value,
    EventType.WORLD_STARTED.value,
)


def simulated_player_presence_filters():
    """SQL filters defining physical presence at a location."""
    return (
        SimulatedPlayer.status
        == SimulatedPlayerStatus.ACTIVE.value,
        SimulatedPlayer.travel_arrival_world_minute.is_(None),
    )


def is_simulated_player_physically_present(
    player: SimulatedPlayer,
) -> bool:
    return (
        player.status
        == SimulatedPlayerStatus.ACTIVE.value
        and player.travel_arrival_world_minute
        is None
    )


def simulated_players_at_location(
    db: Session,
    location_id: str,
) -> list[SimulatedPlayer]:
    return (
        db.query(SimulatedPlayer)
        .filter(
            SimulatedPlayer.location_id
            == location_id,
            *simulated_player_presence_filters(),
        )
        .order_by(SimulatedPlayer.id)
        .all()
    )


def select_existing_simulated_player_for_encounter(
    db: Session,
    campaign_id: str,
    location_id: str,
    rng: random.Random | None = None,
) -> SimulatedPlayer | None:
    """
    Select an already-persistent transported person who is physically
    present at the location.

    This function NEVER creates a new person.
    """

    candidates = [
        player
        for player in simulated_players_at_location(
            db,
            location_id,
        )
        if player.campaign_id == campaign_id
    ]

    if not candidates:
        return None

    r = rng or random.Random()

    return r.choice(candidates)


def simulated_players_in_campaign(
    db: Session,
    campaign_id: str,
) -> list[SimulatedPlayer]:
    return (
        db.query(SimulatedPlayer)
        .filter(
            SimulatedPlayer.campaign_id
            == campaign_id
        )
        .order_by(SimulatedPlayer.id)
        .all()
    )


def _character_has_met_simulated_player(
    db: Session,
    campaign_id: str,
    character_id: str,
    simulated_player_id: str,
) -> bool:
    events = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.actor_type == "character",
            WorldEvent.actor_id == character_id,
            WorldEvent.event_type.in_(
                (
                    EventType.PLAYER_MET_SIMULATED_PLAYER.value,
                    EventType.PLAYER_TALKED_TO_SIMULATED_PLAYER.value,
                )
            ),
        )
        .order_by(
            WorldEvent.created_at.desc(),
            WorldEvent.id.desc(),
        )
        .all()
    )

    for event in events:
        try:
            payload = json.loads(event.payload_json)
        except (json.JSONDecodeError, TypeError):
            continue

        if (
            payload.get("simulated_player_id")
            == simulated_player_id
        ):
            return True

    return False


def meet_simulated_player(
    db: Session,
    campaign_id: str,
    character_id: str,
    simulated_player_id: str,
) -> SimulatedPlayer:
    player = db.get(
        SimulatedPlayer,
        simulated_player_id,
    )

    if (
        player is None
        or player.campaign_id != campaign_id
    ):
        raise ValueError(
            f"Unknown simulated player "
            f"{simulated_player_id}"
        )

    if not is_simulated_player_physically_present(
        player
    ):
        raise ValueError(
            f"Simulated player "
            f"{simulated_player_id} is not present."
        )

    character = db.get(
        Character,
        character_id,
    )

    if (
        character is None
        or character.campaign_id != campaign_id
    ):
        raise ValueError(
            f"Unknown character {character_id}"
        )

    if character.location_id != player.location_id:
        raise ValueError(
            "Character and simulated player "
            "are not at the same location."
        )

    location = db.get(
        Location,
        player.location_id,
    )

    first_meeting = not (
        _character_has_met_simulated_player(
            db,
            campaign_id,
            character_id,
            player.id,
        )
    )

    log_event(
        db,
        campaign_id,
        (
            EventType.PLAYER_MET_SIMULATED_PLAYER
            if first_meeting
            else EventType.PLAYER_TALKED_TO_SIMULATED_PLAYER
        ),
        actor_type="character",
        actor_id=character_id,
        payload={
            "simulated_player_id": player.id,
            "simulated_player_name": player.name,
            "character_name": character.name,
            "location_id": player.location_id,
            "location_name": (
                location.name
                if location
                else "local desconhecido"
            ),
        },
    )

    return player


def get_active_simulated_player_interlocutor(
    db: Session,
    campaign_id: str,
    character_id: str,
    location_id: str,
) -> SimulatedPlayer | None:
    event = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.actor_type == "character",
            WorldEvent.actor_id == character_id,
            WorldEvent.event_type.in_(
                _CONVERSATION_BOUNDARY_EVENTS
            ),
        )
        .order_by(
            WorldEvent.created_at.desc(),
            WorldEvent.id.desc(),
        )
        .first()
    )

    if (
        event is None
        or event.event_type
        not in (
            EventType.PLAYER_MET_SIMULATED_PLAYER.value,
            EventType.PLAYER_TALKED_TO_SIMULATED_PLAYER.value,
        )
    ):
        return None

    try:
        simulated_player_id = json.loads(
            event.payload_json
        ).get(
            "simulated_player_id"
        )
    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return None

    if not simulated_player_id:
        return None

    player = db.get(
        SimulatedPlayer,
        simulated_player_id,
    )

    if (
        player is None
        or player.campaign_id != campaign_id
        or player.location_id != location_id
        or not is_simulated_player_physically_present(
            player
        )
    ):
        return None

    return player