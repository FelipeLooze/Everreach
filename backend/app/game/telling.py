"""What an NPC tells the player in conversation — one rule for every fact.

Before narrating, the engine decides two lists for this turn:

- answers: what the player directly asked and the NPC knows — where they
  are, what the place is called, when a job or contract happens. The
  narration must say them; one the text leaves out is added as a closing
  line (the only case where a line is added).
- related: what the NPC may naturally bring up — the open contracts when
  asked about work, facts about a place or person the player named. Told
  in the NPC's own words if it fits, learned only if actually said, never
  added afterwards.

The player learns exactly what reached the final text. Playtest
(2026-10-24): forcing every loosely matching fact into the reply produced
lines like "— Uma trilha sai de Fenhelm a noroeste em direção a Mata do
Limiar — acrescenta Garrick" after a plain goodbye ("vou na direção que ele
indicou"), and "— Esse contrato se chama ..." when no contract was talked
about.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, KnowerType, KnowledgeCertainty, QuestStatus
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.npc import NPC
from app.db.models.organization import Organization
from app.db.models.quest import Quest
from app.game.npcs.service import knows, teach_fact
from app.game.quests.discovery import is_work_question
from app.game.schedules import is_schedule_question

MAX_FACTS_PER_TURN = 3

_PLACE_QUESTION = re.compile(
    r"\bonde\s+(?:eu\s+)?(?:estou|estamos)\b|\b(?:nome|chama)\b.{0,30}\b(?:vila|lugar|regiao|cidade)\b"
    r"|\b(?:qual|que)\b.{0,20}\b(?:vila|lugar|regiao|cidade)\b"
)
_PLACE_FACT_KEYS = ("settlement_name_known", "settlement_region_known")
_QUESTION = re.compile(
    r"\?|\b(?:onde|como|qual|quais|quem|quando|quanto|sabe|conhece|pode me|me diz|me fala)\b"
)


@dataclass(frozen=True)
class Telling:
    answers: list[KnowledgeFact] = field(default_factory=list)
    related: list[KnowledgeFact] = field(default_factory=list)
    # Extra context per fact (who offers a contract), never taught itself.
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def facts(self) -> list[KnowledgeFact]:
        return [*self.answers, *self.related]

    def context_lines(self, npc_name: str) -> list[str]:
        if not self.facts:
            return []
        lines = [f"WHAT {npc_name.upper()} CAN TELL NOW"]
        if self.answers:
            lines.append("Answers to what was asked — say these:")
            lines += [f"- {fact.statement}{self.notes.get(fact.fact_key, '')}" for fact in self.answers]
        if self.related:
            lines.append("Related — mention only if it fits the conversation naturally:")
            lines += [f"- {fact.statement}{self.notes.get(fact.fact_key, '')}" for fact in self.related]
        lines.append(
            f"{npc_name} speaks naturally, in their own words, keeping each place, person and "
            "contract name. Nothing outside this list is revealed."
        )
        return lines


def _plain(text: str | None) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", (text or "").casefold())
        if not unicodedata.combining(char)
    )


def _names_in(statement: str) -> list[str]:
    """The named things a fact speaks of: capitalized words past the first,
    including quoted titles' words ("Guilda", "Aventureiros", "Limiar")."""
    tokens = re.findall(r"\S+", statement)
    names = re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ'-]{2,}", " ".join(tokens[1:]))
    return [_plain(name) for name in names]


def _npc_facts(db: Session, campaign_id: str, npc_id: str) -> list[KnowledgeFact]:
    return (
        db.query(KnowledgeFact)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.is_secret.is_(False),
            KnowledgeKnower.knower_type == KnowerType.NPC.value,
            KnowledgeKnower.knower_id == npc_id,
        )
        .order_by(KnowledgeFact.fact_key)
        .all()
    )


def _is_open_contract(db: Session, fact: KnowledgeFact) -> bool:
    if not (fact.fact_key.startswith("quest:") and fact.fact_key.endswith(":exists")):
        return False
    quest = db.get(Quest, fact.fact_key.split(":")[1])
    return quest is not None and quest.status == QuestStatus.AVAILABLE


def _names_hit(fact: KnowledgeFact, words: set[str]) -> int:
    """How many of the fact's names the player said ("guildas" ~ "Guilda")."""
    return sum(any(word[:5] == name[:5] for word in words) for name in set(_names_in(fact.statement)))


def decide(db: Session, campaign_id: str, character_id: str, npc, player_input: str) -> Telling:
    """What this NPC can tell now, in answer to this line."""
    facts = [
        fact for fact in _npc_facts(db, campaign_id, npc.id)
        if not knows(db, KnowerType.PLAYER, character_id, fact.fact_key, campaign_id)
    ]
    question = _plain(player_input)
    # Calling someone by name ("Bom dia, Rowan") is not asking about them.
    own_name = set(_plain(npc.name).split())
    words = {word for word in re.findall(r"\w{4,}", question) if word not in own_name}

    answers: list[KnowledgeFact] = []
    if _PLACE_QUESTION.search(question):
        answers += [fact for fact in facts if fact.fact_key in _PLACE_FACT_KEYS]
    if is_schedule_question(player_input):
        schedule_facts = [fact for fact in facts if fact.fact_key.endswith(":schedule")]
        named = [fact for fact in schedule_facts if _names_hit(fact, words) >= 2]
        answers += named or schedule_facts

    related: list[KnowledgeFact] = []
    if is_work_question(player_input):
        contracts = [fact for fact in facts if _is_open_contract(db, fact)]
        # Asked for work, the one who offers a contract answers with it.
        answers += [fact for fact in contracts if _offered_by_npc(db, fact, npc)]
        related += [fact for fact in contracts if fact not in answers]
    if _QUESTION.search(question):
        for fact in facts:
            if fact in answers or fact in related:
                continue
            needed = 2 if _is_open_contract(db, fact) or fact.fact_key.endswith(":schedule") else 1
            if _names_hit(fact, words) >= needed:
                related.append(fact)

    answers = list(dict.fromkeys(answers))[:MAX_FACTS_PER_TURN]
    related = [fact for fact in dict.fromkeys(related) if fact not in answers][: MAX_FACTS_PER_TURN - len(answers)]
    notes = {fact.fact_key: _offered_by(db, fact) for fact in [*answers, *related] if _is_open_contract(db, fact)}
    return Telling(answers, related, notes)


def _offered_by_npc(db: Session, fact: KnowledgeFact, npc) -> bool:
    quest = db.get(Quest, fact.fact_key.split(":")[1])
    sponsor = db.get(Organization, quest.sponsoring_organization_id) if quest and quest.sponsoring_organization_id else None
    return sponsor is not None and sponsor.founder_type == CombatActorType.NPC.value and sponsor.founder_id == npc.id


def _offered_by(db: Session, fact: KnowledgeFact) -> str:
    """Playtest: with only "a guilda" in a contract, the elder credited the
    adventurers' contract to the merchants' guild and its leader."""
    quest = db.get(Quest, fact.fact_key.split(":")[1])
    sponsor = db.get(Organization, quest.sponsoring_organization_id) if quest and quest.sponsoring_organization_id else None
    if sponsor is None:
        return ""
    leader = db.get(NPC, sponsor.founder_id) if sponsor.founder_type == CombatActorType.NPC.value else None
    return f" (offered by {sponsor.name}{f', led by {leader.name}' if leader else ''})"


# --- After narration -----------------------------------------------------------

_HOUR_WORDS = (
    "zero", "uma", "duas", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
    "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito",
    "dezenove", "vinte", "vinte e uma", "vinte e duas", "vinte e tres",
)


def is_stated(statement: str, narrated_text: str) -> bool:
    """Did the narration convey this fact? Lenient on wording: the names are
    what make it this fact (most of them must appear), plus a quoted title
    and the hours of a schedule when the fact has them."""
    text = _plain(narrated_text)
    quoted = re.findall(r'"([^"]+)"', statement)
    if quoted:
        # A contract is identified by its title; its description is context.
        return all(_plain(title) in text for title in quoted)
    hours = re.findall(r"\b(\d{1,2})h\b", statement)
    if hours and not all(
        re.search(rf"\b{hour}\s*h|\b{hour}\s*horas|\b{_HOUR_WORDS[int(hour)]}\b", text) for hour in hours
    ):
        return False
    names = set(_names_in(statement))
    if names:
        said = sum(bool(re.search(rf"\b{re.escape(name)}", text)) for name in names)
        return said * 2 >= len(names)
    return bool(hours)


def tell(db: Session, campaign_id: str, character_id: str, npc, telling: Telling, narrated_text: str) -> str:
    """Add an answer the narration left out; teach what reached the text."""
    for fact in telling.answers:
        if not is_stated(fact.statement, narrated_text):
            verb = "acrescenta" if "—" in narrated_text else "diz"
            narrated_text = f"{narrated_text.rstrip()}\n\n— {fact.statement} — {verb} {npc.name}."
        _teach(db, campaign_id, character_id, npc, fact)
    for fact in telling.related:
        if is_stated(fact.statement, narrated_text):
            _teach(db, campaign_id, character_id, npc, fact)
    return narrated_text


def _teach(db: Session, campaign_id: str, character_id: str, npc, fact: KnowledgeFact) -> None:
    teach_fact(db, campaign_id, fact.fact_key, KnowerType.PLAYER, character_id,
               source=f"revelado por {npc.name}", certainty=KnowledgeCertainty.CONFIRMED)
