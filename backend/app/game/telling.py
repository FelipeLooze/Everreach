"""What an NPC tells the player in conversation — one rule for every fact.

1. Before narrating, the engine decides what the NPC tells NOW: at most a few
   facts that answer the question and that the player does not know yet —
   where they are, the contracts (asked about work), the schedules (asked
   "when?"), otherwise the facts sharing the question's words.
2. The narrator receives them as what must be said.
3. After narrating, any the text left out is added as one line, and the
   player learns exactly these facts.

Before this, the player learned a fact only if the engine could spot it in
the narrated prose (names, quoted titles, directions). Every rewording broke
it: a contract registered without being said, a schedule announced twice.
"""

import re
import unicodedata
from dataclasses import dataclass

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
_STOP_WORDS = frozenset({
    "voce", "voces", "senhor", "senhora", "sobre", "para", "como", "onde", "quando", "qual",
    "quais", "quem", "aqui", "isso", "esse", "essa", "este", "esta", "pode", "posso", "sabe",
    "saber", "tudo", "bem", "obrigado", "obrigada", "favor", "muito", "pouco", "ainda", "mais",
    "tambem", "entao", "alguma", "algum", "alguem", "coisa", "falar", "dizer", "conta", "contar",
    # Linking verbs match every statement ("onde fica a ferraria?" told
    # the elder's line about the creek, which also "fica" somewhere).
    "fica", "ficam", "existe", "existem", "tinha", "estao", "seria", "sera",
})


@dataclass(frozen=True)
class Telling:
    facts: list[KnowledgeFact]
    # Extra context per fact (who offers a contract), never taught itself.
    notes: dict[str, str]

    def context_lines(self, npc_name: str) -> list[str]:
        if not self.facts:
            return []
        return [
            f"WHAT {npc_name.upper()} TELLS NOW",
            *(f"- {fact.statement}{self.notes.get(fact.fact_key, '')}" for fact in self.facts),
            f"{npc_name} answers with exactly this, in natural spoken words, naming every name "
            "and quoted title as written. Nothing else is revealed.",
        ]


def _plain(text: str | None) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", (text or "").casefold())
        if not unicodedata.combining(char)
    )


def _words(text: str) -> list[str]:
    return [word for word in re.findall(r"\w{4,}", _plain(text)) if word not in _STOP_WORDS]


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


def _shares_words(fact: KnowledgeFact, question_words: list[str]) -> int:
    """How many question words a fact speaks of ("guildas" ~ "guilda")."""
    statement_words = _words(fact.statement)
    return sum(
        any(word[:5] == other[:5] for other in statement_words) for word in question_words
    )


def decide(db: Session, campaign_id: str, character_id: str, npc, player_input: str) -> Telling:
    """What this NPC tells now, in answer to this line."""
    facts = [
        fact for fact in _npc_facts(db, campaign_id, npc.id)
        if not knows(db, KnowerType.PLAYER, character_id, fact.fact_key, campaign_id)
    ]
    question = _plain(player_input)
    chosen: list[KnowledgeFact] = []
    if _PLACE_QUESTION.search(question):
        chosen += [fact for fact in facts if fact.fact_key in _PLACE_FACT_KEYS]
    if is_work_question(player_input):
        chosen += [fact for fact in facts if _is_open_contract(db, fact)]
    if is_schedule_question(player_input):
        schedule_facts = [fact for fact in facts if fact.fact_key.endswith(":schedule")]
        named = [fact for fact in schedule_facts if _shares_words(fact, _words(player_input))]
        chosen += named or schedule_facts
    # Calling someone by name ("Bom dia, Rowan") is not asking about them.
    own_name = set(_words(npc.name))
    question_words = [word for word in _words(player_input) if word not in own_name]
    if question_words:
        scored = sorted(
            ((_shares_words(fact, question_words), fact) for fact in facts if fact not in chosen),
            key=lambda pair: (-pair[0], pair[1].fact_key),
        )
        chosen += [fact for score, fact in scored if score > 0]
    chosen = list(dict.fromkeys(chosen))[:MAX_FACTS_PER_TURN]
    return Telling(chosen, {fact.fact_key: _offered_by(db, fact) for fact in chosen if _is_open_contract(db, fact)})


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
    """Did the narration convey this fact? Only decides whether a closing
    line must be added — never whether the player learns it."""
    text = _plain(narrated_text)
    quoted = re.findall(r'"([^"]+)"', statement)
    if quoted:
        return all(_plain(title) in text for title in quoted)
    hours = re.findall(r"\b(\d{1,2})h\b", statement)
    if hours:
        return all(
            re.search(rf"\b{hour}\s*h|\b{hour}\s*horas|\b{_HOUR_WORDS[int(hour)]}\b", text) for hour in hours
        )
    tokens = re.findall(r"\S+", statement)
    names = [
        _plain(word) for word in re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ'-]{2,}", " ".join(tokens[1:]))
    ]
    if names:
        return all(re.search(rf"\b{re.escape(name)}\b", text) for name in names)
    words = _words(statement)
    return bool(words) and sum(word in text for word in words) * 3 >= len(words) * 2


def tell(db: Session, campaign_id: str, character_id: str, npc, telling: Telling, narrated_text: str) -> str:
    """Add what the narration left out, then teach exactly what was told."""
    for fact in telling.facts:
        if not is_stated(fact.statement, narrated_text):
            already_spoke = "—" in narrated_text
            verb = "acrescenta" if already_spoke else "diz"
            narrated_text = f"{narrated_text.rstrip()}\n\n— {fact.statement} — {verb} {npc.name}."
        teach_fact(db, campaign_id, fact.fact_key, KnowerType.PLAYER, character_id,
                   source=f"revelado por {npc.name}", certainty=KnowledgeCertainty.CONFIRMED)
    return narrated_text
