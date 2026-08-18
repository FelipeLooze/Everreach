from sqlalchemy.orm import Session
from app.db.models.event import WorldEvent
from app.core.enums import KnowerType
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower


def explicitly_knows_name(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    name: str | None,
) -> bool:
    """Return whether this knower has a fact that explicitly contains a canonical name."""

    if not name:
        return False

    rows = (
        db.query(KnowledgeFact.statement)
        .join(
            KnowledgeKnower,
            KnowledgeKnower.fact_id == KnowledgeFact.id,
        )
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .all()
    )

    normalized_name = name.casefold()

    return any(
        normalized_name in statement.casefold()
        for (statement,) in rows
    )

def create_event_fact(
    db: Session,
    event: WorldEvent,
    *,
    subject: str,
    statement: str,
    is_secret: bool = False,
) -> KnowledgeFact:
    """
    Create an immutable world-truth fact backed by a structured event.

    Creating the fact does not make any player, NPC, or simulated
    player know it.
    """

    fact_key = f"world_event:{event.id}"

    existing = (
        db.query(KnowledgeFact)
        .filter(
            KnowledgeFact.campaign_id
            == event.campaign_id,
            KnowledgeFact.fact_key
            == fact_key,
        )
        .first()
    )

    if existing is not None:
        return existing

    fact = KnowledgeFact(
        campaign_id=event.campaign_id,
        subject=subject,
        fact_key=fact_key,
        statement=statement,
        is_secret=is_secret,
    )

    db.add(fact)
    db.flush()

    return fact
