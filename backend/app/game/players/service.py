import json
import random

from sqlalchemy.orm import Session
from app.db.models.simulated_player_arrival import (
    ScheduledSimulatedPlayerArrival,
    SimulatedPlayerArrivalPolicy,
)
from app.game.time.clock import get_world_time
from app.core.enums import (
    EventType,
    SimulatedPlayerStatus,
)
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.db.models.location import Location
from app.db.models.region import Region
from app.db.models.simulated_player import (
    SimulatedPlayer,
    SimulatedPlayerPopulation,
)
from app.services.event_log import log_event
from app.db.models.campaign import Campaign

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

def _require_location_in_campaign(
    db: Session,
    campaign_id: str,
    location_id: str,
) -> Location:
    location = db.get(
        Location,
        location_id,
    )

    if location is None:
        raise ValueError(
            f"Unknown location {location_id}"
        )

    region = db.get(
        Region,
        location.region_id,
    )

    if (
        region is None
        or region.campaign_id != campaign_id
    ):
        raise ValueError(
            f"Location {location_id} does not belong "
            f"to campaign {campaign_id}"
        )

    return location


def abstract_simulated_player_count_at_location(
    db: Session,
    campaign_id: str,
    location_id: str,
) -> int:
    _require_location_in_campaign(
        db,
        campaign_id,
        location_id,
    )

    population = (
        db.query(SimulatedPlayerPopulation)
        .filter(
            SimulatedPlayerPopulation.location_id
            == location_id
        )
        .first()
    )

    if population is None:
        return 0

    return population.abstract_count


def set_abstract_simulated_player_population(
    db: Session,
    campaign_id: str,
    location_id: str,
    count: int,
) -> SimulatedPlayerPopulation:
    _require_location_in_campaign(
        db,
        campaign_id,
        location_id,
    )

    if count < 0:
        raise ValueError(
            "Abstract simulated player population "
            "cannot be negative."
        )

    population = (
        db.query(SimulatedPlayerPopulation)
        .filter(
            SimulatedPlayerPopulation.location_id
            == location_id
        )
        .first()
    )

    if population is None:
        population = SimulatedPlayerPopulation(
            location_id=location_id,
        )
        db.add(population)

    population.abstract_count = count

    db.flush()

    return population

def consume_abstract_simulated_player_population(
    db: Session,
    campaign_id: str,
    location_id: str,
) -> SimulatedPlayerPopulation:
    _require_location_in_campaign(
        db,
        campaign_id,
        location_id,
    )

    population = (
        db.query(SimulatedPlayerPopulation)
        .filter(
            SimulatedPlayerPopulation.location_id
            == location_id
        )
        .first()
    )

    if (
        population is None
        or population.abstract_count <= 0
    ):
        raise ValueError(
            "No abstract simulated player population "
            "is available at this location."
        )

    population.abstract_count -= 1

    db.flush()

    return population

def register_simulated_player_world_arrival(
    db: Session,
    campaign_id: str,
    location_id: str,
    count: int,
    *,
    occurred_world_minute: int | None = None,
) -> SimulatedPlayerPopulation:
    """
    Register newly transported people arriving in the world.

    They enter only as abstract population. Individual identities are
    materialized later when an actual encounter requires one.
    """

    location = _require_location_in_campaign(
        db,
        campaign_id,
        location_id,
    )

    if count <= 0:
        raise ValueError(
            "Arrival count must be greater than zero."
        )

    population = (
        db.query(SimulatedPlayerPopulation)
        .filter(
            SimulatedPlayerPopulation.location_id
            == location_id
        )
        .first()
    )

    if population is None:
        population = SimulatedPlayerPopulation(
            location_id=location_id,
            abstract_count=0,
        )
        db.add(population)

    population.abstract_count += count

    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_WORLD_ARRIVAL,
        actor_type="world",
        payload={
            "location_id": location.id,
            "location_name": location.name,
            "count": count,
        },
        occurred_world_minute=occurred_world_minute,
    )

    return population

def schedule_simulated_player_world_arrival(
    db: Session,
    campaign_id: str,
    location_id: str,
    count: int,
    scheduled_world_minute: int,
) -> ScheduledSimulatedPlayerArrival:
    """
    Schedule a future arrival.

    This only creates the schedule. It does not add abstract population
    and does not create individual transported people.
    """

    _require_location_in_campaign(
        db,
        campaign_id,
        location_id,
    )

    if count <= 0:
        raise ValueError(
            "Arrival count must be greater than zero."
        )

    current_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    if scheduled_world_minute <= current_world_minute:
        raise ValueError(
            "Scheduled arrival must be in the future."
        )

    arrival = ScheduledSimulatedPlayerArrival(
        location_id=location_id,
        scheduled_world_minute=scheduled_world_minute,
        count=count,
        executed_world_minute=None,
    )

    db.add(arrival)
    db.flush()

    return arrival


def schedule_next_simulated_player_world_arrival(
    db: Session,
    campaign_id: str,
    location_id: str,
    count: int,
    min_delay_minutes: int,
    max_delay_minutes: int,
    rng: random.Random | None = None,
) -> ScheduledSimulatedPlayerArrival:
    """
    Schedule an irregular future arrival inside a caller-provided window.

    This function defines the scheduling mechanism, not the world's
    canonical arrival frequency or group size.
    """

    if min_delay_minutes <= 0:
        raise ValueError(
            "Minimum arrival delay must be greater than zero."
        )

    if max_delay_minutes < min_delay_minutes:
        raise ValueError(
            "Maximum arrival delay cannot be smaller "
            "than minimum arrival delay."
        )

    current_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    random_source = rng or random.Random()

    delay_minutes = random_source.randint(
        min_delay_minutes,
        max_delay_minutes,
    )

    return schedule_simulated_player_world_arrival(
        db,
        campaign_id,
        location_id,
        count,
        current_world_minute + delay_minutes,
    )

def get_simulated_player_arrival_policy(
    db: Session,
    campaign_id: str,
) -> SimulatedPlayerArrivalPolicy | None:
    return (
        db.query(SimulatedPlayerArrivalPolicy)
        .filter(
            SimulatedPlayerArrivalPolicy.campaign_id
            == campaign_id
        )
        .first()
    )


def set_simulated_player_arrival_policy(
    db: Session,
    campaign_id: str,
    *,
    enabled: bool,
    min_delay_minutes: int,
    max_delay_minutes: int,
    min_group_size: int,
    max_group_size: int,
) -> SimulatedPlayerArrivalPolicy:
    """
    Create or update the campaign's later-arrival policy.

    This only stores configuration. It does not schedule or execute
    an arrival.
    """

    campaign = db.get(
        Campaign,
        campaign_id,
    )

    if campaign is None:
        raise ValueError(
            f"Campaign {campaign_id} does not exist."
        )

    if min_delay_minutes <= 0:
        raise ValueError(
            "Minimum arrival delay must be greater than zero."
        )

    if max_delay_minutes < min_delay_minutes:
        raise ValueError(
            "Maximum arrival delay cannot be smaller "
            "than minimum arrival delay."
        )

    if min_group_size <= 0:
        raise ValueError(
            "Minimum arrival group size must be greater than zero."
        )

    if max_group_size < min_group_size:
        raise ValueError(
            "Maximum arrival group size cannot be smaller "
            "than minimum arrival group size."
        )

    policy = get_simulated_player_arrival_policy(
        db,
        campaign_id,
    )

    if policy is None:
        policy = SimulatedPlayerArrivalPolicy(
            campaign_id=campaign_id,
            enabled=enabled,
            min_delay_minutes=min_delay_minutes,
            max_delay_minutes=max_delay_minutes,
            min_group_size=min_group_size,
            max_group_size=max_group_size,
        )

        db.add(policy)

    else:
        policy.enabled = enabled
        policy.min_delay_minutes = min_delay_minutes
        policy.max_delay_minutes = max_delay_minutes
        policy.min_group_size = min_group_size
        policy.max_group_size = max_group_size

    db.flush()

    return policy

def schedule_simulated_player_world_arrival_from_policy(
    db: Session,
    campaign_id: str,
    location_id: str,
    rng: random.Random | None = None,
) -> ScheduledSimulatedPlayerArrival | None:
    """
    Schedule one future arrival using the campaign policy.

    The caller still decides the arrival location.

    No policy or a disabled policy means no automatic arrival
    is scheduled.
    """

    policy = get_simulated_player_arrival_policy(
        db,
        campaign_id,
    )

    if policy is None or not policy.enabled:
        return None

    random_source = rng or random.Random()

    count = random_source.randint(
        policy.min_group_size,
        policy.max_group_size,
    )

    return schedule_next_simulated_player_world_arrival(
        db,
        campaign_id,
        location_id,
        count=count,
        min_delay_minutes=policy.min_delay_minutes,
        max_delay_minutes=policy.max_delay_minutes,
        rng=random_source,
    )

def get_pending_simulated_player_world_arrival(
    db: Session,
    campaign_id: str,
) -> ScheduledSimulatedPlayerArrival | None:
    return (
        db.query(ScheduledSimulatedPlayerArrival)
        .join(
            Location,
            ScheduledSimulatedPlayerArrival.location_id
            == Location.id,
        )
        .join(
            Region,
            Location.region_id == Region.id,
        )
        .filter(
            Region.campaign_id == campaign_id,
            ScheduledSimulatedPlayerArrival.executed_world_minute
            .is_(None),
        )
        .order_by(
            ScheduledSimulatedPlayerArrival.scheduled_world_minute,
            ScheduledSimulatedPlayerArrival.id,
        )
        .first()
    )

def ensure_simulated_player_world_arrival_scheduled(
    db: Session,
    campaign_id: str,
    location_id: str,
    rng: random.Random | None = None,
) -> ScheduledSimulatedPlayerArrival | None:
    """
    Ensure the campaign has at most one pending automatic arrival.

    The caller still decides the location.
    """

    existing = get_pending_simulated_player_world_arrival(
        db,
        campaign_id,
    )

    if existing is not None:
        return existing

    return schedule_simulated_player_world_arrival_from_policy(
        db,
        campaign_id,
        location_id,
        rng=rng,
    )