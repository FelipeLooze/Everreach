import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterStatus,
    CombatActorType,
    CombatAwareness,
    CombatEncounterStatus,
    CombatRangeBand,
    EventType,
    SimulatedPlayerStatus,
)
from app.db.models.campaign import Campaign
from app.db.models.character import Character
from app.db.models.combat import CombatEncounter, CombatParticipant
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.region import Region
from app.db.models.simulated_player import SimulatedPlayer
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


_SIDE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_TERMINAL_STATUSES = {
    CombatEncounterStatus.VICTORY,
    CombatEncounterStatus.DEFEAT,
    CombatEncounterStatus.FLED,
    CombatEncounterStatus.CANCELLED,
}


class CombatEncounterError(ValueError):
    pass


@dataclass(frozen=True)
class CombatantSpec:
    actor_type: CombatActorType
    actor_id: str
    side_key: str
    range_band: CombatRangeBand = CombatRangeBand.NEAR
    awareness: CombatAwareness = CombatAwareness.AWARE


def start_encounter(
    db: Session,
    campaign_id: str,
    location_id: str,
    combatants: tuple[CombatantSpec, ...],
) -> CombatEncounter:
    """Start one encounter from concrete, co-located and living actors."""
    _validate_location(db, campaign_id, location_id)
    if len(combatants) < 2:
        raise CombatEncounterError("Combat requires at least two participants.")
    normalized = tuple(_normalize_spec(spec) for spec in combatants)
    actor_keys = {(spec.actor_type.value, spec.actor_id) for spec in normalized}
    if len(actor_keys) != len(normalized):
        raise CombatEncounterError("Combat participant is duplicated.")
    if len({spec.side_key for spec in normalized}) < 2:
        raise CombatEncounterError("Combat requires at least two distinct sides.")

    for spec in normalized:
        _validate_actor(db, campaign_id, location_id, spec)
        if get_active_encounter_for_actor(
            db,
            spec.actor_type,
            spec.actor_id,
        ) is not None:
            raise CombatEncounterError("Actor is already in an active combat.")

    world_minute = get_world_time(db, campaign_id).total_minutes()
    encounter = CombatEncounter(
        campaign_id=campaign_id,
        location_id=location_id,
        status=CombatEncounterStatus.ACTIVE.value,
        round_number=0,
        started_world_minute=world_minute,
        end_reason="",
    )
    db.add(encounter)
    db.flush()
    for spec in normalized:
        _add_participant_row(db, encounter, spec, world_minute)
    log_event(
        db,
        campaign_id,
        EventType.COMBAT_STARTED,
        actor_type="combat",
        actor_id=encounter.id,
        payload={
            "encounter_id": encounter.id,
            "location_id": location_id,
            "participants": [
                {
                    "actor_type": spec.actor_type.value,
                    "actor_id": spec.actor_id,
                    "side_key": spec.side_key,
                }
                for spec in normalized
            ],
        },
        importance=3,
    )
    db.flush()
    return encounter


def add_participant(
    db: Session,
    encounter: CombatEncounter,
    spec: CombatantSpec,
) -> CombatParticipant:
    _require_active(encounter)
    normalized = _normalize_spec(spec)
    _validate_actor(
        db,
        encounter.campaign_id,
        encounter.location_id,
        normalized,
    )
    if get_active_encounter_for_actor(
        db,
        normalized.actor_type,
        normalized.actor_id,
    ) is not None:
        raise CombatEncounterError("Actor is already in an active combat.")
    world_minute = get_world_time(
        db,
        encounter.campaign_id,
    ).total_minutes()
    participant = (
        db.query(CombatParticipant)
        .filter(
            CombatParticipant.encounter_id == encounter.id,
            CombatParticipant.actor_type == normalized.actor_type.value,
            CombatParticipant.actor_id == normalized.actor_id,
        )
        .one_or_none()
    )
    if participant is None:
        participant = _add_participant_row(
            db,
            encounter,
            normalized,
            world_minute,
        )
    else:
        participant.side_key = normalized.side_key
        participant.range_band = normalized.range_band.value
        participant.awareness = normalized.awareness.value
        participant.active = True
        participant.joined_world_minute = world_minute
        participant.left_world_minute = None
        participant.left_reason = ""
        participant.initiative_roll = None
        participant.initiative_modifier = None
        participant.initiative_score = None
        participant.turn_order = None
    if encounter.round_number > 0:
        from app.game.combat.turns import enroll_late_participant

        enroll_late_participant(db, encounter, participant)
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_PARTICIPANT_JOINED,
        actor_type=normalized.actor_type.value.lower(),
        actor_id=normalized.actor_id,
        payload={
            "encounter_id": encounter.id,
            "side_key": normalized.side_key,
        },
        importance=2,
    )
    db.flush()
    return participant


def remove_participant(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    *,
    reason: str,
) -> CombatParticipant:
    _require_active(encounter)
    if participant.encounter_id != encounter.id:
        raise CombatEncounterError("Participant does not belong to encounter.")
    if not participant.active:
        return participant
    normalized_reason = " ".join(reason.split())
    if not normalized_reason:
        raise CombatEncounterError("Participant exit reason is required.")
    participant.active = False
    participant.left_world_minute = get_world_time(
        db,
        encounter.campaign_id,
    ).total_minutes()
    participant.left_reason = normalized_reason
    from app.game.combat.conditions import remove_participant_conditions

    remove_participant_conditions(
        db,
        encounter,
        participant,
        reason=f"participant_left:{normalized_reason}",
    )
    if encounter.round_number > 0:
        from app.game.combat.turns import skip_current_turn_if_inactive

        skip_current_turn_if_inactive(db, encounter)
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_PARTICIPANT_LEFT,
        actor_type=participant.actor_type.lower(),
        actor_id=participant.actor_id,
        payload={
            "encounter_id": encounter.id,
            "reason": normalized_reason,
        },
        importance=2,
    )
    db.flush()
    return participant


def end_encounter(
    db: Session,
    encounter: CombatEncounter,
    status: CombatEncounterStatus,
    *,
    reason: str,
) -> CombatEncounter:
    if not isinstance(status, CombatEncounterStatus) or status not in _TERMINAL_STATUSES:
        raise CombatEncounterError("Combat requires a terminal end status.")
    normalized_reason = " ".join(reason.split())
    if not normalized_reason:
        raise CombatEncounterError("Combat end reason is required.")
    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        if encounter.status == status.value and encounter.end_reason == normalized_reason:
            return encounter
        raise CombatEncounterError("Combat encounter has already ended.")

    world_minute = get_world_time(
        db,
        encounter.campaign_id,
    ).total_minutes()
    encounter.status = status.value
    encounter.ended_world_minute = world_minute
    encounter.end_reason = normalized_reason
    from app.game.combat.conditions import remove_encounter_conditions

    remove_encounter_conditions(
        db,
        encounter,
        reason=f"encounter_ended:{status.value.lower()}",
    )
    if encounter.round_number > 0:
        from app.game.combat.turns import close_active_turn

        close_active_turn(db, encounter)
    for participant in list_active_participants(db, encounter.id):
        participant.active = False
        participant.left_world_minute = world_minute
        participant.left_reason = f"encounter:{status.value.lower()}"
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_ENDED,
        actor_type="combat",
        actor_id=encounter.id,
        payload={
            "encounter_id": encounter.id,
            "status": status.value,
            "reason": normalized_reason,
            "round_number": encounter.round_number,
        },
        importance=3,
    )
    db.flush()
    return encounter


def get_active_encounter_for_actor(
    db: Session,
    actor_type: CombatActorType,
    actor_id: str,
) -> CombatEncounter | None:
    if not isinstance(actor_type, CombatActorType):
        raise CombatEncounterError("Invalid combat actor type.")
    matches = (
        db.query(CombatEncounter)
        .join(CombatParticipant)
        .filter(
            CombatEncounter.status == CombatEncounterStatus.ACTIVE.value,
            CombatParticipant.actor_type == actor_type.value,
            CombatParticipant.actor_id == actor_id,
            CombatParticipant.active.is_(True),
        )
        .order_by(CombatEncounter.created_at, CombatEncounter.id)
        .all()
    )
    if len(matches) > 1:
        raise CombatEncounterError("Actor belongs to multiple active combats.")
    return matches[0] if matches else None


def list_active_participants(
    db: Session,
    encounter_id: str,
) -> list[CombatParticipant]:
    return (
        db.query(CombatParticipant)
        .filter(
            CombatParticipant.encounter_id == encounter_id,
            CombatParticipant.active.is_(True),
        )
        .order_by(CombatParticipant.id)
        .all()
    )


def _normalize_spec(spec: CombatantSpec) -> CombatantSpec:
    if not isinstance(spec.actor_type, CombatActorType):
        raise CombatEncounterError("Invalid combat actor type.")
    if not isinstance(spec.range_band, CombatRangeBand):
        raise CombatEncounterError("Invalid combat range band.")
    if not isinstance(spec.awareness, CombatAwareness):
        raise CombatEncounterError("Invalid combat awareness.")
    actor_id = spec.actor_id.strip()
    side_key = spec.side_key.strip().lower()
    if not actor_id:
        raise CombatEncounterError("Combat actor id is required.")
    if not _SIDE_KEY_PATTERN.fullmatch(side_key):
        raise CombatEncounterError("Invalid combat side key.")
    return CombatantSpec(
        actor_type=spec.actor_type,
        actor_id=actor_id,
        side_key=side_key,
        range_band=spec.range_band,
        awareness=spec.awareness,
    )


def _validate_location(db: Session, campaign_id: str, location_id: str) -> None:
    if db.get(Campaign, campaign_id) is None:
        raise CombatEncounterError("Campaign does not exist.")
    location = (
        db.query(Location)
        .join(Region, Region.id == Location.region_id)
        .filter(
            Location.id == location_id,
            Region.campaign_id == campaign_id,
        )
        .one_or_none()
    )
    if location is None:
        raise CombatEncounterError("Combat location does not belong to campaign.")


def _validate_actor(
    db: Session,
    campaign_id: str,
    location_id: str,
    spec: CombatantSpec,
) -> None:
    if spec.actor_type == CombatActorType.CHARACTER:
        actor = db.get(Character, spec.actor_id)
        valid = (
            actor is not None
            and actor.campaign_id == campaign_id
            and actor.location_id == location_id
            and actor.status != CharacterStatus.DEAD.value
        )
    elif spec.actor_type == CombatActorType.NPC:
        actor = db.get(NPC, spec.actor_id)
        valid = (
            actor is not None
            and actor.campaign_id == campaign_id
            and actor.location_id == location_id
            and actor.alive
        )
    else:
        actor = db.get(SimulatedPlayer, spec.actor_id)
        valid = (
            actor is not None
            and actor.campaign_id == campaign_id
            and actor.location_id == location_id
            and actor.status != SimulatedPlayerStatus.DEAD.value
        )
    if not valid:
        raise CombatEncounterError(
            "Combat actor must be living and present at the encounter location."
        )


def _add_participant_row(
    db: Session,
    encounter: CombatEncounter,
    spec: CombatantSpec,
    world_minute: int,
) -> CombatParticipant:
    participant = CombatParticipant(
        encounter_id=encounter.id,
        actor_type=spec.actor_type.value,
        actor_id=spec.actor_id,
        side_key=spec.side_key,
        range_band=spec.range_band.value,
        awareness=spec.awareness.value,
        active=True,
        joined_world_minute=world_minute,
        left_reason="",
    )
    db.add(participant)
    db.flush()
    return participant


def _require_active(encounter: CombatEncounter) -> None:
    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        raise CombatEncounterError("Combat encounter is not active.")
