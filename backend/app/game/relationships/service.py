from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.campaign import WorldTime
from app.db.models.relationship import (
    CharacterNPCRelationship,
    CharacterSimulatedPlayerRelationship,
    SimulatedPlayerRelationship,
)
from app.db.models.simulated_player import SimulatedPlayer
from app.services.event_log import log_event


def get_character_npc_relationship(
    db: Session, campaign_id: str, character_id: str, npc_id: str
) -> CharacterNPCRelationship | None:
    return (
        db.query(CharacterNPCRelationship)
        .filter(
            CharacterNPCRelationship.campaign_id == campaign_id,
            CharacterNPCRelationship.character_id == character_id,
            CharacterNPCRelationship.npc_id == npc_id,
        )
        .first()
    )


def get_character_simulated_player_relationship(
    db: Session,
    campaign_id: str,
    character_id: str,
    simulated_player_id: str,
) -> CharacterSimulatedPlayerRelationship | None:
    return (
        db.query(CharacterSimulatedPlayerRelationship)
        .filter(
            CharacterSimulatedPlayerRelationship.campaign_id
            == campaign_id,
            CharacterSimulatedPlayerRelationship.character_id
            == character_id,
            CharacterSimulatedPlayerRelationship.simulated_player_id
            == simulated_player_id,
        )
        .first()
    )


def record_npc_interaction(
    db: Session,
    campaign_id: str,
    character_id: str,
    npc_id: str,
    *,
    familiarity_delta: int = 1,
    trust_delta: int = 0,
    affinity_delta: int = 0,
) -> CharacterNPCRelationship:
    relationship = get_character_npc_relationship(
        db, campaign_id, character_id, npc_id
    )
    if relationship is None:
        relationship = CharacterNPCRelationship(
            campaign_id=campaign_id,
            character_id=character_id,
            npc_id=npc_id,
            familiarity=0,
            trust=0,
            affinity=0,
            last_interaction_minute=0,
        )
        db.add(relationship)

    relationship.familiarity = max(
        0, min(100, relationship.familiarity + familiarity_delta)
    )
    relationship.trust = max(-100, min(100, relationship.trust + trust_delta))
    relationship.affinity = max(-100, min(100, relationship.affinity + affinity_delta))
    world_time = db.query(WorldTime).filter(WorldTime.campaign_id == campaign_id).first()
    relationship.last_interaction_minute = world_time.total_minutes() if world_time else 0
    relationship.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.RELATIONSHIP_CHANGED,
        actor_type="character",
        actor_id=character_id,
        payload={
            "npc_id": npc_id,
            "familiarity_delta": familiarity_delta,
            "trust_delta": trust_delta,
            "affinity_delta": affinity_delta,
            "familiarity": relationship.familiarity,
            "trust": relationship.trust,
            "affinity": relationship.affinity,
        },
        importance=2,
    )
    return relationship


def record_simulated_player_interaction(
    db: Session,
    campaign_id: str,
    character_id: str,
    simulated_player_id: str,
    *,
    familiarity_delta: int = 1,
    trust_delta: int = 0,
    affinity_delta: int = 0,
) -> CharacterSimulatedPlayerRelationship:
    relationship = (
        get_character_simulated_player_relationship(
            db,
            campaign_id,
            character_id,
            simulated_player_id,
        )
    )

    if relationship is None:
        relationship = CharacterSimulatedPlayerRelationship(
            campaign_id=campaign_id,
            character_id=character_id,
            simulated_player_id=simulated_player_id,
            familiarity=0,
            trust=0,
            affinity=0,
            last_interaction_minute=0,
        )
        db.add(relationship)

    relationship.familiarity = max(
        0,
        min(
            100,
            relationship.familiarity
            + familiarity_delta,
        ),
    )

    relationship.trust = max(
        -100,
        min(
            100,
            relationship.trust
            + trust_delta,
        ),
    )

    relationship.affinity = max(
        -100,
        min(
            100,
            relationship.affinity
            + affinity_delta,
        ),
    )

    world_time = (
        db.query(WorldTime)
        .filter(
            WorldTime.campaign_id == campaign_id
        )
        .first()
    )

    relationship.last_interaction_minute = (
        world_time.total_minutes()
        if world_time
        else 0
    )

    relationship.updated_at = datetime.now(
        UTC
    ).replace(
        tzinfo=None
    )

    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.RELATIONSHIP_CHANGED,
        actor_type="character",
        actor_id=character_id,
        payload={
            "simulated_player_id": simulated_player_id,
            "familiarity_delta": familiarity_delta,
            "trust_delta": trust_delta,
            "affinity_delta": affinity_delta,
            "familiarity": relationship.familiarity,
            "trust": relationship.trust,
            "affinity": relationship.affinity,
        },
        importance=2,
    )

    return relationship

def simulated_player_relationship_behavior_guidance(
    relationship: CharacterSimulatedPlayerRelationship,
) -> tuple[str, str]:
    """
    Derive private behavioral guidance from authoritative
    relationship values.

    These values influence behavior but never override
    personality, goals, safety, interests, or free choice.
    """

    if relationship.trust <= -50:
        trust_guidance = (
            "Strong distrust: avoid relying on the player, "
            "be guarded with vulnerable information, and "
            "question the player's intentions when relevant."
        )
    elif relationship.trust <= -20:
        trust_guidance = (
            "Low trust: be cautious about relying on the player "
            "or sharing vulnerable information without reason."
        )
    elif relationship.trust >= 50:
        trust_guidance = (
            "Strong trust: may rely on or confide in the player "
            "more readily when doing so fits personality, goals, "
            "safety, and circumstances."
        )
    elif relationship.trust >= 20:
        trust_guidance = (
            "Growing trust: may be somewhat more willing to rely "
            "on the player or share personal information when justified."
        )
    else:
        trust_guidance = (
            "Neutral trust: do not apply a special trust or distrust bias."
        )

    if relationship.affinity <= -50:
        affinity_guidance = (
            "Strong negative affinity: interaction may be cold, irritated, "
            "or reluctant, without forcing hostility or violence."
        )
    elif relationship.affinity <= -20:
        affinity_guidance = (
            "Negative affinity: tend toward a cooler, less welcoming "
            "interaction when circumstances allow."
        )
    elif relationship.affinity >= 50:
        affinity_guidance = (
            "Strong positive affinity: interaction may be notably warm "
            "and voluntarily engaged, without overriding other motives."
        )
    elif relationship.affinity >= 20:
        affinity_guidance = (
            "Positive affinity: tend toward a warmer and more voluntarily "
            "engaged interaction when circumstances allow."
        )
    else:
        affinity_guidance = (
            "Neutral affinity: do not apply a special warmth or hostility bias."
        )

    return trust_guidance, affinity_guidance

def simulated_player_reencounter_weight(
    relationship: CharacterSimulatedPlayerRelationship | None,
) -> int:
    """
    Weight a socially plausible reencounter without affecting
    physical presence, travel, availability, or eligibility.

    Affinity has the stronger influence because it more directly
    affects willingness to engage socially. Trust is a smaller
    modifier.
    """

    if relationship is None:
        return 10

    weight = 10

    if relationship.affinity <= -50:
        weight -= 6
    elif relationship.affinity <= -20:
        weight -= 3
    elif relationship.affinity >= 50:
        weight += 8
    elif relationship.affinity >= 20:
        weight += 4

    if relationship.trust <= -50:
        weight -= 2
    elif relationship.trust <= -20:
        weight -= 1
    elif relationship.trust >= 50:
        weight += 3
    elif relationship.trust >= 20:
        weight += 1

    return max(1, weight)


def _ordered_simulated_player_ids(first_id: str, second_id: str) -> tuple[str, str]:
    if first_id == second_id:
        raise ValueError("A person cannot have a relationship with itself.")
    return tuple(sorted((first_id, second_id)))


def get_simulated_player_relationship(
    db: Session,
    campaign_id: str,
    first_id: str,
    second_id: str,
) -> SimulatedPlayerRelationship | None:
    ordered_first, ordered_second = _ordered_simulated_player_ids(first_id, second_id)
    return (
        db.query(SimulatedPlayerRelationship)
        .filter(
            SimulatedPlayerRelationship.campaign_id == campaign_id,
            SimulatedPlayerRelationship.first_player_id == ordered_first,
            SimulatedPlayerRelationship.second_player_id == ordered_second,
        )
        .first()
    )


def record_simulated_players_interaction(
    db: Session,
    campaign_id: str,
    first_id: str,
    second_id: str,
    *,
    familiarity_delta: int = 1,
    trust_delta: int = 0,
    affinity_delta: int = 0,
    occurred_world_minute: int | None = None,
) -> SimulatedPlayerRelationship:
    ordered_first, ordered_second = _ordered_simulated_player_ids(first_id, second_id)
    people = (
        db.query(SimulatedPlayer.id)
        .filter(
            SimulatedPlayer.campaign_id == campaign_id,
            SimulatedPlayer.id.in_((ordered_first, ordered_second)),
        )
        .count()
    )
    if people != 2:
        raise ValueError("Both simulated players must belong to the campaign.")

    relationship = get_simulated_player_relationship(
        db, campaign_id, ordered_first, ordered_second
    )
    if relationship is None:
        relationship = SimulatedPlayerRelationship(
            campaign_id=campaign_id,
            first_player_id=ordered_first,
            second_player_id=ordered_second,
            familiarity=0,
            trust=0,
            affinity=0,
            last_interaction_minute=0,
        )
        db.add(relationship)
    relationship.familiarity = max(
        0, min(100, relationship.familiarity + familiarity_delta)
    )
    relationship.trust = max(-100, min(100, relationship.trust + trust_delta))
    relationship.affinity = max(
        -100, min(100, relationship.affinity + affinity_delta)
    )
    world_time = db.query(WorldTime).filter(WorldTime.campaign_id == campaign_id).first()
    relationship.last_interaction_minute = (
        occurred_world_minute
        if occurred_world_minute is not None
        else (world_time.total_minutes() if world_time else 0)
    )
    relationship.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.flush()
    log_event(
        db,
        campaign_id,
        EventType.RELATIONSHIP_CHANGED,
        actor_type="simulated_player",
        actor_id=ordered_first,
        payload={
            "other_simulated_player_id": ordered_second,
            "familiarity": relationship.familiarity,
            "trust": relationship.trust,
            "affinity": relationship.affinity,
        },
        importance=2,
        occurred_world_minute=relationship.last_interaction_minute,
    )
    return relationship
