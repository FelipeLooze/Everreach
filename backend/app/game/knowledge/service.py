from sqlalchemy.orm import Session

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
