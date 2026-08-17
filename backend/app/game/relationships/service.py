from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.campaign import WorldTime
from app.db.models.relationship import CharacterNPCRelationship
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
