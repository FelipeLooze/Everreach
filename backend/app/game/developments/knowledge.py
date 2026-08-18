import json

from sqlalchemy.orm import Session
from app.db.models.npc import NPC
from app.core.enums import EventType
from app.db.models.event import WorldEvent
from app.db.models.knowledge import KnowledgeFact
from app.game.knowledge.service import create_event_fact


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