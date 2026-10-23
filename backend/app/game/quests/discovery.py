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

import re
import unicodedata

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


_WORK_QUESTION_PATTERN = re.compile(
    r"\b(?:trabalhos?|empregos?|servicos?|contratos?|miss(?:ao|oes)|tarefas?|oportunidades?)\b"
)


def is_work_question(text: str) -> bool:
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", (text or "").casefold())
        if not unicodedata.combining(char)
    )
    return _WORK_QUESTION_PATTERN.search(normalized) is not None


def open_quests_known_by_npc(db: Session, campaign_id: str, npc_id: str) -> list:
    """Open contracts this NPC knows of — what they can tell when asked
    about work."""
    from app.core.enums import QuestStatus
    from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
    from app.db.models.quest import Quest

    fact_keys = (
        db.query(KnowledgeFact.fact_key)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.fact_key.like("quest:%:exists"),
            KnowledgeKnower.knower_type == KnowerType.NPC.value,
            KnowledgeKnower.knower_id == npc_id,
        )
        .order_by(KnowledgeFact.fact_key)
        .all()
    )
    quests = [db.get(Quest, fact_key.split(":")[1]) for (fact_key,) in fact_keys]
    return [quest for quest in quests if quest is not None and quest.status == QuestStatus.AVAILABLE]


def _mentions_title(text: str, title: str) -> bool:
    def normalized(value: str) -> str:
        return "".join(
            char for char in unicodedata.normalize("NFKD", value.casefold())
            if not unicodedata.combining(char)
        )

    return normalized(title) in normalized(text)


def tell_contracts(
    db: Session, campaign_id: str, character_id: str, npc, narrated_text: str
) -> str:
    """Asked about work, the NPC tells the open contracts they know. Any the
    narration left out is added as one closing line, and the player learns
    exactly the contracts named in the final text — never one that was not
    said (playtest: asking the elder about work registered a contract he
    never mentioned)."""
    quests = open_quests_known_by_npc(db, campaign_id, npc.id)
    # Only contracts the player hasn't heard of yet need saying again:
    # "E quando dá para fazer esse contrato?" must not re-announce it.
    missing = [
        quest for quest in quests
        if not _mentions_title(narrated_text, quest.name)
        and not is_quest_known_to_character(db, campaign_id, character_id, quest.id)
    ]
    if missing:
        titles = " e ".join(f'"{quest.name}"' for quest in missing)
        noun = "os contratos" if len(missing) > 1 else "o contrato"
        already_spoke = "—" in narrated_text
        opening, verb = ("Também há", "acrescenta") if already_spoke else ("Há", "diz")
        narrated_text = f"{narrated_text.rstrip()}\n\n— {opening} {noun} {titles} — {verb} {npc.name}."
    for quest in quests:
        if _mentions_title(narrated_text, quest.name):
            learn_about_quest_from_npc(db, campaign_id, character_id, quest.id)
    return narrated_text
