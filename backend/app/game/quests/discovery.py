"""Phase 12J — Quest Discovery & Knowledge.

Three genuinely separate things, per the spec's own critical distinction:
Quest exists (a Quest row — Phase 12A) != Character knows Quest exists
(this module, via the existing Knowledge system) != Character knows all
Quest details (never modeled — the Knowledge system's single statement +
certainty gradient is deliberately coarse; a deep partial-information
system is explicitly out of scope, see the spec's HIDDEN OBJECTIVES and
FALSE/MISLEADING NOTICES sections).

Nothing here invents a new knowledge mechanism — every function is a thin,
source-specific wrapper around the Phase 4/5 Knowledge system
(teach_fact/knows), reusing quest_existence_fact_key from
app.game.quests.service so a Quest's existence fact and its discovery
never drift apart. Two real sources are wired: reading a linked Notice
(Phase 12I, CONFIRMED — a physically read posting is about as reliable as
world information gets) and NPC dialogue (BELIEVED by default — what an
NPC says is their belief, not automatically ground truth, matching how
the rest of the Knowledge system already treats NPC-sourced facts).
"""

from sqlalchemy.orm import Session

from app.core.enums import KnowerType, KnowledgeCertainty
from app.game.npcs.service import knows, teach_fact
from app.game.quests.service import quest_existence_fact_key


def is_quest_known_to_character(db: Session, campaign_id: str, character_id: str, quest_id: str) -> bool:
    return knows(db, KnowerType.PLAYER, character_id, quest_existence_fact_key(quest_id), campaign_id)


def learn_about_quest_from_notice(
    db: Session, campaign_id: str, character_id: str, quest_id: str
) -> None:
    """A character reading a real posting linked to this quest (Phase
    12I) — the most reliable discovery source, since the posting is a
    physical object the character directly perceived."""
    teach_fact(
        db,
        campaign_id,
        quest_existence_fact_key(quest_id),
        KnowerType.PLAYER,
        character_id,
        source="notice_board",
        certainty=KnowledgeCertainty.CONFIRMED,
    )


def learn_about_quest_from_npc(
    db: Session,
    campaign_id: str,
    character_id: str,
    quest_id: str,
    *,
    certainty: KnowledgeCertainty = KnowledgeCertainty.BELIEVED,
) -> None:
    """An NPC telling a character about a situation — defaults to BELIEVED,
    not CONFIRMED, since what an NPC says is their belief, not
    automatically ground truth (the spec's NPC KNOWLEDGE AND QUEST
    INFORMATION section). A caller with a reason to trust the NPC more (or
    less) may override certainty explicitly."""
    teach_fact(
        db,
        campaign_id,
        quest_existence_fact_key(quest_id),
        KnowerType.PLAYER,
        character_id,
        source="npc_dialogue",
        certainty=certainty,
    )
