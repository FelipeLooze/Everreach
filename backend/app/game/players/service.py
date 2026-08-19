import random
from sqlalchemy.orm import Session
from app.core.enums import SimulatedPlayerStatus
from app.db.models.simulated_player import SimulatedPlayer


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