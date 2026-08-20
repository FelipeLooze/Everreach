from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.campaign import WorldTime
from app.services.event_log import log_event

SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12


def get_world_time(db: Session, campaign_id: str) -> WorldTime:
    world_time = db.query(WorldTime).filter(WorldTime.campaign_id == campaign_id).first()
    if world_time is None:
        raise ValueError(f"Campaign {campaign_id} has no world time initialized.")
    return world_time


def advance_world_time_seconds(
    db: Session,
    campaign_id: str,
    seconds: int,
) -> int:
    """
    Accumulate subminute elapsed time.

    Returns the number of whole world minutes crossed.
    Only whole crossed minutes should advance minute-based
    world simulation.
    """

    if seconds <= 0:
        return 0

    world_time = get_world_time(
        db,
        campaign_id,
    )

    total_seconds = (
        world_time.subminute_seconds
        + seconds
    )

    crossed_minutes = (
        total_seconds // SECONDS_PER_MINUTE
    )

    world_time.subminute_seconds = (
        total_seconds % SECONDS_PER_MINUTE
    )

    if crossed_minutes > 0:
        advance_world_time(
            db,
            campaign_id,
            crossed_minutes,
        )

    return crossed_minutes


def advance_world_time(db: Session, campaign_id: str, minutes: int) -> WorldTime:
    """Advance the in-world clock. Actions consume time; this is the single place
    time moves forward, so simulation/NPC ticks can hook off of it deterministically."""
    if minutes <= 0:
        return get_world_time(db, campaign_id)

    world_time = get_world_time(db, campaign_id)

    total = world_time.minute + minutes
    world_time.minute = total % MINUTES_PER_HOUR
    carry_hours = total // MINUTES_PER_HOUR

    total_hours = world_time.hour + carry_hours
    world_time.hour = total_hours % HOURS_PER_DAY
    carry_days = total_hours // HOURS_PER_DAY

    total_days = world_time.day - 1 + carry_days
    world_time.day = (total_days % DAYS_PER_MONTH) + 1
    carry_months = total_days // DAYS_PER_MONTH

    total_months = world_time.month - 1 + carry_months
    world_time.month = (total_months % MONTHS_PER_YEAR) + 1
    carry_years = total_months // MONTHS_PER_YEAR

    world_time.year += carry_years

    log_event(
        db,
        campaign_id,
        EventType.WORLD_TIME_ADVANCED,
        actor_type="world",
        payload={"minutes": minutes},
    )

    return world_time
