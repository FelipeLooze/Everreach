import json
from sqlalchemy.orm import Session
from app.db.models.npc import NPC
from app.db.models.event import WorldEvent
from app.db.models.knowledge import KnowledgeFact
from app.db.models.character import Character
from app.game.time.clock import get_world_time
from app.game.knowledge.service import create_event_fact
from app.game.npcs.service import teach_fact
from app.core.enums import (
    CharacterStatus,
    EventType,
    KnowledgeCertainty,
    KnowerType,
)


def create_development_event_fact(
    db: Session,
    event: WorldEvent,
) -> KnowledgeFact:
    payload = json.loads(
        event.payload_json or "{}"
    )

    title = payload.get(
        "title",
        "Um desenvolvimento do mundo",
    )

    subject = (
        f"world_development:{event.actor_id}"
    )

    if (
        event.event_type
        == EventType.WORLD_DEVELOPMENT_CREATED.value
    ):
        statement = (
            f"{title} começou."
        )

    elif (
        event.event_type
        == EventType.WORLD_DEVELOPMENT_UPDATED.value
    ):
        progress = payload.get("progress")

        statement = (
            f"{title} atingiu {progress}% de progresso."
        )

    elif (
        event.event_type
        == EventType.WORLD_DEVELOPMENT_COMPLETED.value
    ):
        statement = (
            f"{title} foi concluído."
        )

    else:
        raise ValueError(
            "event is not a world development event"
        )

    return create_event_fact(
        db,
        event,
        subject=subject,
        statement=statement,
    )

def local_npc_witnesses(
    db: Session,
    event: WorldEvent,
) -> list[NPC]:

    if not can_resolve_direct_witnesses(
        db,
        event,
    ):
        return []
    
    payload = json.loads(
        event.payload_json or "{}"
    )

    location_id = payload.get(
        "location_id"
    )

    if location_id is None:
        return []

    return (
        db.query(NPC)
        .filter(
            NPC.campaign_id == event.campaign_id,
            NPC.location_id == location_id,
            NPC.alive.is_(True),
        )
        .order_by(NPC.id)
        .all()
    )

def local_character_witnesses(
    db: Session,
    event: WorldEvent,
) -> list[Character]:

    if not can_resolve_direct_witnesses(
        db,
        event,
    ):
        return []
    
    payload = json.loads(
        event.payload_json or "{}"
    )

    location_id = payload.get(
        "location_id"
    )

    if location_id is None:
        return []

    return (
        db.query(Character)
        .filter(
            Character.campaign_id == event.campaign_id,
            Character.location_id == location_id,
            Character.status
            == CharacterStatus.ALIVE.value,
        )
        .order_by(Character.id)
        .all()
    )

def teach_development_fact_to_local_witnesses(
    db: Session,
    event: WorldEvent,
    fact: KnowledgeFact,
) -> None:
    for npc in local_npc_witnesses(
        db,
        event,
    ):
        teach_fact(
            db,
            event.campaign_id,
            fact.fact_key,
            KnowerType.NPC,
            npc.id,
            source="percepção direta",
            certainty=KnowledgeCertainty.CONFIRMED,
        )

    for character in local_character_witnesses(
        db,
        event,
    ):
        teach_fact(
            db,
            event.campaign_id,
            fact.fact_key,
            KnowerType.PLAYER,
            character.id,
            source="percepção direta",
            certainty=KnowledgeCertainty.CONFIRMED,
        )

def can_resolve_direct_witnesses(
    db: Session,
    event: WorldEvent,
) -> bool:
    current_world_minute = get_world_time(
        db,
        event.campaign_id,
    ).total_minutes()

    return (
        event.world_minute
        == current_world_minute
    )