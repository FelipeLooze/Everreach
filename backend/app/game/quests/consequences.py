"""Phase 12E — Consequences.

World-state changes caused by a quest resolving one way or another —
completion, failure, abandonment. Deliberately narrow to what already has
a real backend system to apply through: Relationships and Knowledge.
Organization/economic/political consequences (Phase 13/14) have no system
yet to apply them into, so they are not modeled as a type here — quest
content simply cannot declare them until those systems exist.

This mirrors the Phase 11 ProgressionOutcome pattern: calling code builds
a small, typed bag of what happened; one function here is the sole
authority that actually applies it, by delegating to the existing
Relationships/Knowledge services rather than mutating anything directly.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import KnowerType, KnowledgeCertainty
from app.game.npcs.service import teach_fact
from app.game.relationships.service import record_npc_interaction


@dataclass(frozen=True)
class RelationshipConsequence:
    npc_id: str
    familiarity_delta: int = 0
    trust_delta: int = 0
    affinity_delta: int = 0


@dataclass(frozen=True)
class KnowledgeConsequence:
    fact_key: str
    knower_type: KnowerType
    knower_id: str
    certainty: KnowledgeCertainty = KnowledgeCertainty.CONFIRMED


@dataclass(frozen=True)
class QuestConsequences:
    relationships: tuple[RelationshipConsequence, ...] = ()
    knowledge: tuple[KnowledgeConsequence, ...] = ()


def apply_quest_consequences(
    db: Session,
    campaign_id: str,
    character_id: str,
    consequences: QuestConsequences | None,
) -> None:
    """Apply a QuestConsequences bag, if any. character_id is the
    protagonist whose quest resolution caused these — every
    RelationshipConsequence here is between that character and the named
    NPC (a quest's consequences are always framed from its resolver's
    point of view)."""
    if consequences is None:
        return
    for relationship in consequences.relationships:
        record_npc_interaction(
            db,
            campaign_id,
            character_id,
            relationship.npc_id,
            familiarity_delta=relationship.familiarity_delta,
            trust_delta=relationship.trust_delta,
            affinity_delta=relationship.affinity_delta,
        )
    for fact in consequences.knowledge:
        teach_fact(
            db,
            campaign_id,
            fact.fact_key,
            fact.knower_type,
            fact.knower_id,
            source="quest_consequence",
            certainty=fact.certainty,
        )
