import math
import random
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.core.enums import (
    DiscoveryStatus,
    EventType,
    TravelIncidentKind,
    TravelPace,
)
from app.db.models.location import Location, LocationConnection
from app.game.discovery.service import (
    get_connection_discovery,
    get_location_discovery,
    set_location_discovery,
)
from app.game.items.encumbrance import get_character_encumbrance
from app.game.world.materialization import ensure_location_materialized
from app.services.event_log import log_event

BASE_MINUTES_PER_DISTANCE = 15
DEFAULT_TRAVEL_SPEED_MULTIPLIER = 1.0

BASE_STAMINA_PER_DISTANCE = 2.0

BASE_DANGER_HAZARD_PER_HOUR = 0.10

PACE_SPEED_MULTIPLIERS = {
    TravelPace.SLOW: 0.75,
    TravelPace.NORMAL: 1.0,
    TravelPace.FAST: 1.5,
}


PACE_STAMINA_MULTIPLIERS = {
    TravelPace.SLOW: 0.75,
    TravelPace.NORMAL: 1.0,
    TravelPace.FAST: 1.75,
}

class TravelError(ValueError):
    pass

@dataclass(frozen=True)
class TravelRiskResult:
    chance: float
    roll: float
    triggered: bool

@dataclass(frozen=True)
class TravelIncident:
    kind: TravelIncidentKind
    extra_minutes: int = 0
    extra_stamina: float = 0.0

@dataclass(frozen=True)
class TravelResult:
    minutes: int
    base_minutes: int
    stamina_spent: float
    risk: TravelRiskResult
    incident: TravelIncident | None = None

def calculate_travel_incident_chance(
    connection: LocationConnection,
    minutes: int,
) -> float:
    """Calculate the probability of a travel incident.

    `danger` is an exposure intensity, not a direct percentage.

    Longer journeys and more dangerous routes increase exposure.
    Danger 0 always means no random travel incident.
    """

    if minutes <= 0 or connection.danger <= 0:
        return 0.0

    hours = minutes / 60

    exposure = (
        BASE_DANGER_HAZARD_PER_HOUR
        * connection.danger
        * hours
    )

    chance = 1.0 - math.exp(-exposure)

    return max(
        0.0,
        min(1.0, chance),
    )

def calculate_travel_minutes(
    connection: LocationConnection,
    speed_multiplier: float = DEFAULT_TRAVEL_SPEED_MULTIPLIER,
) -> int:
    """Calculate deterministic travel time for one physical route.

    distance:
        Physical length of the route.

    travel_time_modifier:
        Difficulty of traversing the route itself.
        Values above 1.0 make travel slower.
        Values below 1.0 make travel faster.

    speed_multiplier:
        How fast the traveler is currently moving.
        1.0 means normal walking speed.
        Values above 1.0 are faster.
        Values below 1.0 are slower.
    """

    if speed_multiplier <= 0:
        raise TravelError(
            "O multiplicador de velocidade deve ser maior que zero."
        )

    raw_minutes = (
        BASE_MINUTES_PER_DISTANCE
        * connection.distance
        * connection.travel_time_modifier
        / speed_multiplier
    )

    return max(1, round(raw_minutes))

def calculate_travel_stamina_cost(
    connection: LocationConnection,
    pace: TravelPace = TravelPace.NORMAL,
    encumbrance_multiplier: float = 1.0,
) -> float:
    """Calculate the physical stamina cost of traversing one route."""

    pace = TravelPace(pace)
    if not math.isfinite(encumbrance_multiplier) or encumbrance_multiplier < 1.0:
        raise TravelError("O multiplicador de carga não pode ser menor que um.")

    raw_cost = (
        BASE_STAMINA_PER_DISTANCE
        * connection.distance
        * connection.travel_time_modifier
        * PACE_STAMINA_MULTIPLIERS[pace]
        * encumbrance_multiplier
    )

    return round(max(0.1, raw_cost), 1)

def find_connection(
    db: Session,
    from_location_id: str,
    to_location_id: str,
) -> LocationConnection | None:
    return (
        db.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == from_location_id,
            LocationConnection.to_location_id == to_location_id,
            LocationConnection.active.is_(True),
        )
        .first()
    )


def move_character(
    db: Session,
    campaign_id: str,
    character,
    to_location_id: str,
    speed_multiplier: float = DEFAULT_TRAVEL_SPEED_MULTIPLIER,
    pace: TravelPace = TravelPace.NORMAL,
    rng: random.Random | None = None,
) -> TravelResult:
    """Move a character to a connected and known location.

    Returns the structured mechanical result of the journey.

    Raises TravelError when:
    - there is no active physical connection;
    - the character does not know that connection;
    - the destination does not exist.
    """

    from_location_id = character.location_id

    connection = find_connection(
        db,
        from_location_id,
        to_location_id,
    )

    if connection is None:
        raise TravelError(
            "Nenhum caminho liga a localização atual a esse destino."
        )

    connection_discovery = get_connection_discovery(
        db,
        character.id,
        connection.id,
    )

    if connection_discovery is None:
        raise TravelError(
            "Você conhece o destino, mas não conhece uma rota utilizável até ele."
        )

    destination = db.get(
        Location,
        to_location_id,
    )

    if destination is None:
        raise TravelError(
            "Destino desconhecido."
        )

    # Phase 15N — content-on-demand: a Tier 2 stub (Phase 15F minor
    # settlement) gets deep-materialized the moment something actually
    # requires its detail to exist — here, the character arriving. A
    # no-op for anything already Tier 1.
    destination = ensure_location_materialized(db, destination)

    try:
        pace = TravelPace(pace)
    except ValueError as exc:
        raise TravelError(
            "Ritmo de viagem inválido."
        ) from exc

    pace_speed_multiplier = PACE_SPEED_MULTIPLIERS[pace]

    effective_speed_multiplier = (
        speed_multiplier
        * pace_speed_multiplier
    )

    base_minutes = calculate_travel_minutes(
        connection,
        effective_speed_multiplier,
    )

    encumbrance = get_character_encumbrance(db, character.id)
    stamina_cost = calculate_travel_stamina_cost(
        connection,
        pace,
        encumbrance.stamina_multiplier,
    )

    if character.stamina_current < stamina_cost:
        raise TravelError(
            "Você está cansado demais para percorrer essa rota nesse ritmo."
    )

    risk = roll_travel_incident(
        connection,
        base_minutes,
        rng=rng,
    )

    incident = None

    if risk.triggered:
        incident = choose_travel_incident(
            connection,
            base_minutes,
            rng=rng,
        )

    extra_minutes = (
        incident.extra_minutes
        if incident is not None
        else 0
    )

    extra_stamina = (
        incident.extra_stamina
        if incident is not None
        else 0.0
    )

    minutes = base_minutes + extra_minutes

    total_stamina_cost = round(
        stamina_cost + extra_stamina,
        1,
    )

    previous_discovery = get_location_discovery(
        db,
        character.id,
        destination.id,
    )

    previous_status = (
        DiscoveryStatus(previous_discovery.status)
        if previous_discovery is not None
        else None
    )

    newly_discovered = (
        previous_status is None
        or previous_status == DiscoveryStatus.RUMORED
    )

    first_visit = (
        previous_status is None
        or previous_status
        in (
            DiscoveryStatus.RUMORED,
            DiscoveryStatus.DISCOVERED,
        )
    )

    character.stamina_current = max(
        0.0,
        character.stamina_current - total_stamina_cost,
    )

    # Move o personagem.
    character.location_id = destination.id
    character.region_id = destination.region_id

    # Marca o destino como visitado apenas para este personagem.
    set_location_discovery(
        db,
        character.id,
        destination.id,
        DiscoveryStatus.VISITED,
    )

    # Registra o incidente ocorrido durante o percurso, se houver.
    if incident is not None:
        log_event(
            db,
            campaign_id,
            EventType.TRAVEL_INCIDENT,
            actor_type="character",
            actor_id=character.id,
            payload={
                "connection_id": connection.id,
                "from_location_id": from_location_id,
                "to_location_id": destination.id,
                "kind": incident.kind.value,
                "chance": risk.chance,
                "roll": risk.roll,
                "extra_minutes": incident.extra_minutes,
                "extra_stamina": incident.extra_stamina,
            },
        )

    # Toda viagem realizada gera PLAYER_MOVED.
    log_event(
        db,
        campaign_id,
        EventType.PLAYER_MOVED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "from_location_id": from_location_id,
            "to_location_id": destination.id,
            "base_minutes": base_minutes,
            "minutes": minutes,
            "pace": pace.value,
            "stamina_spent": total_stamina_cost,
            "incident": incident.kind.value if incident else None,
        },
    )

    # Caso excepcional: chegou a um lugar que ainda não estava realmente descoberto.
    if newly_discovered:
        log_event(
            db,
            campaign_id,
            EventType.LOCATION_DISCOVERED,
            actor_type="character",
            actor_id=character.id,
            payload={
                "location_id": destination.id,
                "source": "travel",
            },
        )

    # Primeira vez que o personagem entra fisicamente neste lugar.
    if first_visit:
        log_event(
            db,
            campaign_id,
            EventType.LOCATION_VISITED,
            actor_type="character",
            actor_id=character.id,
            payload={
                "location_id": destination.id,
                "from_location_id": from_location_id,
            },
        )

    return TravelResult(
        minutes=minutes,
        base_minutes=base_minutes,
        stamina_spent=total_stamina_cost,
        risk=risk,
        incident=incident,
    )

def roll_travel_incident(
    connection: LocationConnection,
    minutes: int,
    rng: random.Random | None = None,
) -> TravelRiskResult:
    """Roll whether an incident occurs during one journey."""

    chance = calculate_travel_incident_chance(
        connection,
        minutes,
    )

    roller = rng or random

    roll = roller.random()

    return TravelRiskResult(
        chance=chance,
        roll=roll,
        triggered=roll < chance,
    )

def choose_travel_incident(
    connection: LocationConnection,
    base_minutes: int,
    rng: random.Random | None = None,
) -> TravelIncident:
    """Choose one backend-authoritative non-combat travel incident."""

    roller = rng or random

    if roller.random() < 0.5:
        extra_minutes = max(
            5,
            round(base_minutes * 0.25),
        )

        return TravelIncident(
            kind=TravelIncidentKind.DELAY,
            extra_minutes=extra_minutes,
        )

    extra_stamina = round(
        max(
            0.5,
            BASE_STAMINA_PER_DISTANCE
            * connection.distance
            * connection.travel_time_modifier
            * 0.5,
        ),
        1,
    )

    return TravelIncident(
        kind=TravelIncidentKind.FATIGUE,
        extra_stamina=extra_stamina,
    )
