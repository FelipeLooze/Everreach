import json

from sqlalchemy.orm import Session

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