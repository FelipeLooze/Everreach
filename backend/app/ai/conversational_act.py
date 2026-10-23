"""Phase 24E — Conversational Act Grounding.

Phase 24A.1's own docstring on `_looks_like_direct_question` explicitly
deferred a real conversational-act classifier to Phase 24E: this module
is that classifier. It represents what the player is conversationally
*doing* this turn (greeting, asking for a name, asking for a location,
saying goodbye, ...) as one small deterministic label — not a dialogue
tree, not an LLM call, not hundreds of hardcoded intents.

The exact player utterance stays authoritative everywhere (narrator.py
still quotes it verbatim). The classified act only supplements it, by
letting the current-turn grounding instructions react to a few cases
where the previous single "is this a question?" boolean was too coarse
(e.g. a farewell needs different grounding than a question does, even
though today both may be phrased as a question-shaped sentence).
"""
from enum import Enum
import re
import unicodedata

from app.game.world.content_pools import SETTLEMENT_SERVICE_POOL


class ConversationalAct(str, Enum):
    GREETING = "GREETING"
    QUESTION_NAME = "QUESTION_NAME"
    QUESTION_LOCATION = "QUESTION_LOCATION"
    QUESTION_PERSON = "QUESTION_PERSON"
    QUESTION_OBJECT = "QUESTION_OBJECT"
    REQUEST_HELP = "REQUEST_HELP"
    REQUEST_INFORMATION = "REQUEST_INFORMATION"
    STATEMENT = "STATEMENT"
    FAREWELL = "FAREWELL"


# Acts that pose an explicit question the interlocutor must address (answer,
# refuse, or admit not knowing) rather than silently ignore.
QUESTION_ACTS = frozenset(
    {
        ConversationalAct.QUESTION_NAME,
        ConversationalAct.QUESTION_LOCATION,
        ConversationalAct.QUESTION_PERSON,
        ConversationalAct.QUESTION_OBJECT,
        ConversationalAct.REQUEST_INFORMATION,
    }
)

_QUESTION_WORDS = re.compile(
    r"\b(qual|quais|quem|onde|como|quando|por\s*que|porque|quanto|quantos|quantas)\b",
    re.IGNORECASE,
)
_NAME_WORDS = re.compile(r"\bnome\b|\bchama\b", re.IGNORECASE)
_LOCATION_WORDS = re.compile(r"\bonde\b|\blugar\b|\bcidade\b|\bvila\b|\bregi[ãa]o\b", re.IGNORECASE)
_OBJECT_WORDS = re.compile(r"\bo\s+que\s+[ée]\b|\bisso\b|\bisto\b", re.IGNORECASE)
_PERSON_WORDS = re.compile(r"\bquem\b|\bvoc[êe]\s+[ée]\b", re.IGNORECASE)
_HELP_PATTERN = re.compile(r"\bajud\w*\b|\bsocorro\b", re.IGNORECASE)
_INFO_REQUEST_PATTERN = re.compile(
    r"^\s*(me\s+)?(conte|diga|fale|explique|descreva)\b", re.IGNORECASE
)
_FAREWELL_PATTERN = re.compile(
    r"\b(tchau|adeus|at[ée]\s+(logo|mais|breve|a\s+pr[óo]xima))\b", re.IGNORECASE
)
_GREETING_PATTERN = re.compile(
    r"^\s*(ol[áa]|oi|e\s*a[íi]|bom\s+dia|boa\s+tarde|boa\s+noite|sauda[çc][õo]es)\b",
    re.IGNORECASE,
)
# Distinguishes "qual o SEU nome" (about the interlocutor) from "qual o
# nome dessa VILA" (about something else entirely) — both are "asking
# about a name" at the act level; only this marker tells them apart.
_SELF_REFERENCE_MARKERS = re.compile(r"\b(seu|sua|voc[êe]|voc[êe]s|teu|tua)\b", re.IGNORECASE)


class ConversationalSubject(str, Enum):
    """Phase 24J.1 — what a question/request is actually ABOUT, layered on
    top of `ConversationalAct` rather than replacing it. The act alone is
    too coarse for relevance checking: `classify()` buckets "qual o SEU
    nome?" and "qual o nome dessa VILA?" into the same QUESTION_NAME act
    (both ask about "a name"), but only a subject dimension can tell them
    apart well enough to check the response against the right fact.

    Deliberately a small, broad set — the smallest structured vocabulary
    that lets relevance validation pick the right acceptance signal (the
    NPC's own name vs. the settlement's canonical name vs. some other
    person entirely), never hundreds of specific-topic enums. The exact
    player utterance stays the authoritative record everywhere else; this
    is a routing hint, not a paraphrase of what was asked.
    """

    SELF_NAME = "SELF_NAME"
    CURRENT_SETTLEMENT = "CURRENT_SETTLEMENT"
    CURRENT_LOCATION = "CURRENT_LOCATION"
    PERSON = "PERSON"
    OBJECT = "OBJECT"
    ORGANIZATION = "ORGANIZATION"
    DIRECTION = "DIRECTION"
    SERVICE = "SERVICE"
    EVENT = "EVENT"
    GENERIC_INFORMATION = "GENERIC_INFORMATION"
    NONE = "NONE"


_HERE_REFERENCE = re.compile(
    r"\b(aqui|esta|este|desta|deste|nesta|neste|essa|esse|dessa|desse|nessa|nesse)\b",
    re.IGNORECASE,
)
_SETTLEMENT_WORDS = re.compile(
    r"\bvila\b|\bcidade\b|\baldeia\b|\bvilarejo\b|\bpovoado\b", re.IGNORECASE
)
_LOCATION_GENERIC_WORDS = re.compile(
    r"\blugar\b|\bregi[ãa]o\b|\bonde\s+estamos\b|\bonde\s+(eu\s+)?estou\b", re.IGNORECASE
)
_ORG_WORDS = re.compile(
    r"\bguilda\b|\bconselho\b|\bordem\b|\bimp[ée]rio\b|\breino\b|\bfacc?[ãa]o\b|\birmandade\b",
    re.IGNORECASE,
)
_DIRECTION_WORDS = re.compile(
    r"\bcomo\s+chego\b|\bcaminho\b|\bdire[çc][ãa]o\b|\bfica\s+onde\b|\bpor\s+onde\b",
    re.IGNORECASE,
)
_SERVICE_WORDS = re.compile(
    r"\bloja\b|\bcomprar\b|\bvender\b|\btaverna\b|\bestalagem\b|\bpre[çc]o\b|\bhospedagem\b|\bquarto\b"
    # Phase 24J.4 — "ferraria"/"ferreiro" were entirely absent: a question
    # like "existe uma ferraria aqui?" fell through to a different subject
    # bucket and got neither the relevance nor the factual-denial checks
    # this whole subject exists to gate. The spec's own required test case
    # ("is there a blacksmith?") needs this.
    r"|\bferraria\b|\bferreir[oa]\b",
    re.IGNORECASE,
)
_EVENT_WORDS = re.compile(
    r"\baconteceu\b|\bfestival\b|\bguerra\b|\bataque\b|\bcelebra[çc][ãa]o\b", re.IGNORECASE
)
_OBJECT_REFERENCE = re.compile(r"\bisso\b|\bisto\b|\baquil[oa]\b", re.IGNORECASE)
_QUESTION_OR_REQUEST_ACTS = QUESTION_ACTS | frozenset({ConversationalAct.REQUEST_HELP})


def classify_subject(player_input: str) -> ConversationalSubject:
    """Deterministic, cheap, single-label subject classification — same
    style and constraints as `classify()` (regex only, no LLM call, no
    semantic parse). Only meaningful for acts that actually ask/request
    something; GREETING/STATEMENT/FAREWELL always resolve to NONE."""
    text = player_input.strip()
    if not text:
        return ConversationalSubject.NONE

    act = classify(text)
    if act not in _QUESTION_OR_REQUEST_ACTS:
        return ConversationalSubject.NONE

    has_name_word = bool(_NAME_WORDS.search(text))
    has_here_ref = bool(_HERE_REFERENCE.search(text))
    is_self = bool(_SELF_REFERENCE_MARKERS.search(text))
    is_settlement = bool(_SETTLEMENT_WORDS.search(text))

    if has_name_word and is_settlement:
        return ConversationalSubject.CURRENT_SETTLEMENT
    if has_name_word and is_self:
        return ConversationalSubject.SELF_NAME
    if is_settlement and has_here_ref:
        return ConversationalSubject.CURRENT_SETTLEMENT
    if _DIRECTION_WORDS.search(text):
        return ConversationalSubject.DIRECTION
    if _LOCATION_GENERIC_WORDS.search(text) or (
        has_here_ref and re.search(r"\bonde\b", text, re.IGNORECASE)
    ):
        return ConversationalSubject.CURRENT_LOCATION
    if _ORG_WORDS.search(text):
        return ConversationalSubject.ORGANIZATION
    if _SERVICE_WORDS.search(text):
        return ConversationalSubject.SERVICE
    if _EVENT_WORDS.search(text):
        return ConversationalSubject.EVENT
    if has_name_word or _PERSON_WORDS.search(text):
        return ConversationalSubject.PERSON
    if _OBJECT_WORDS.search(text) or _OBJECT_REFERENCE.search(text):
        return ConversationalSubject.OBJECT
    return ConversationalSubject.GENERIC_INFORMATION


def _normalized_subject_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


# Phase 24J.4 — Issue 2 (False Factual Denial). Which SPECIFIC service a
# SERVICE-subject question is about, and whether it's an existence/
# availability question specifically (as opposed to e.g. a price question
# about a service already known to exist). Every service type's PRIMARY
# alias comes directly from SETTLEMENT_SERVICE_POOL's own label — the
# single source of truth for what a service is actually called, zero risk
# of drifting out of sync with world content — with only a small,
# hand-maintained set of well-established colloquial synonyms layered on
# top for the types a player would naturally phrase differently.
_SERVICE_TYPE_SYNONYMS_PT: dict[str, tuple[str, ...]] = {
    # Simplification Pass S1.3 — "quarto" (room) added: the spec's own
    # primary price example ("Quanto custa um quarto?") names the room,
    # not the inn itself, and had no alias resolving it to "inn" at all.
    "inn": ("hospedagem", "pousada", "quarto"),
    "blacksmith": ("ferreiro", "ferreira"),
    "shop": ("loja",),
}

_SERVICE_TYPE_ALIASES_PT: dict[str, tuple[str, ...]] = {
    service_type: (_normalized_subject_text(label),) + _SERVICE_TYPE_SYNONYMS_PT.get(service_type, ())
    for label, service_type, _description in SETTLEMENT_SERVICE_POOL.values()
}

_SERVICE_TYPE_ALIAS_LOOKUP: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            (_normalized_subject_text(alias), service_type)
            for service_type, aliases in _SERVICE_TYPE_ALIASES_PT.items()
            for alias in aliases
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)


def service_type_asked_about(player_input: str) -> str | None:
    """Which SETTLEMENT_SERVICE_POOL type key (if any) this text names,
    by exact-alias match — never a guess. Longest alias first so "loja
    geral" matches whole rather than being pre-empted by the shorter
    "loja"."""
    normalized = _normalized_subject_text(player_input)
    for alias, service_type in _SERVICE_TYPE_ALIAS_LOOKUP:
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return service_type
    return None


_EXISTENCE_QUESTION_PATTERN = re.compile(
    r"\bexiste\b|\bha\b|\btem\b|\bpossui\b|\bhouve\b", re.IGNORECASE
)


# Simplification Pass S1.3 — PRICE grounding. Two shapes: a price WORD
# present anywhere ("preço", "diária", "valor" — covers "Esse quarto é
# quanto a diária?", where "quanto" and the price word are not adjacent),
# or the bare quantity word "quanto" paired with a small set of common
# price-asking verbs regardless of order ("Quanto custa?"/"Quanto é?"/
# "Quanto fica?"/"Quanto sai?"/"É quanto?") — "quanto" alone is too
# generic (e.g. "quantos quartos existem" asks a count, not a price).
_PRICE_WORDS_PATTERN = re.compile(r"\bpre[çc]o\b|\bdi[áa]ria\b|\bvalor\b", re.IGNORECASE)
_PRICE_QUANTITY_WORD = re.compile(r"\bquanto\b", re.IGNORECASE)
# "paga"/"ganha"/"recebe": a wage question; context_builder grounds those
# separately (the job's pay), before any service price.
_PRICE_VERB_PATTERN = re.compile(
    r"\bcusta\b|\b[ée]\b|\bfica\b|\bsai\b|\bvale\b|\bpaga\b|\bpagam\b|\bganha\b|\brecebe\b",
    re.IGNORECASE,
)


def is_price_question(player_input: str) -> bool:
    """True for "Quanto custa?"/"Qual o preço?"/"Quanto é a diária?"/
    "Quanto fica?"/"Esse quarto é quanto a diária?"/"Quanto é?" — false
    for an unrelated question that merely mentions a service in passing.
    Deliberately narrow, same discipline as is_existence_question: a
    question this doesn't recognize simply isn't covered by PRICE
    grounding, not a false-positive risk either way."""
    normalized = _normalized_subject_text(player_input)
    if _PRICE_WORDS_PATTERN.search(normalized):
        return True
    return bool(
        _PRICE_QUANTITY_WORD.search(normalized) and _PRICE_VERB_PATTERN.search(normalized)
    )


# Economic subjects are domain concepts, not phrase-specific intents.  This
# deliberately small vocabulary routes generic services through one S1.3
# materializer while exact conversational wording remains authoritative.
_ECONOMIC_SERVICE_ALIASES: dict[str, tuple[str, ...]] = {
    "lodging": ("quarto", "hospedagem", "pousada", "diaria", "estalagem"),
    "meal": ("refeicao", "comida", "prato", "jantar", "almoco"),
    "repair": ("reparo", "conserto", "manutencao"),
    "transport": ("transporte", "passagem", "viagem"),
    "stabling": ("estabulo", "estabulagem", "cavalo"),
    "healing": ("cura", "tratamento", "atendimento"),
    "crafting": ("fabricacao", "encomenda", "artesanato"),
    "labor": ("trabalho", "mao de obra", "servico profissional"),
    "rental": ("aluguel", "locacao"),
}


def economic_service_asked_about(player_input: str) -> str | None:
    normalized = _normalized_subject_text(player_input)
    for key, aliases in _ECONOMIC_SERVICE_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            return key
    return None


def is_existence_question(player_input: str) -> bool:
    """True for "existe/tem/há uma estalagem?" — false for a price/
    directions/other question that merely mentions a service in passing.
    Deliberately narrow (per the governing spec's own instruction: prefer
    known entities + known aliases over general parsing) — a question
    this doesn't recognize simply isn't covered by the factual-denial
    check, not a false positive risk either way."""
    return bool(_EXISTENCE_QUESTION_PATTERN.search(_normalized_subject_text(player_input)))


def classify(player_input: str) -> ConversationalAct:
    """Deterministic, cheap, single-label classification. Order matters:
    an explicit question always wins over an incidental greeting/farewell
    phrased in the same sentence (e.g. "Olá, qual o seu nome?" is a
    QUESTION_NAME, not a GREETING) — answering what was actually asked is
    the behavior Phase 24A.1 fixed, and this must not regress it.
    """
    text = player_input.strip()
    if not text:
        return ConversationalAct.STATEMENT

    is_question = "?" in text or bool(_QUESTION_WORDS.search(text))
    if is_question:
        if _NAME_WORDS.search(text):
            return ConversationalAct.QUESTION_NAME
        if _LOCATION_WORDS.search(text):
            return ConversationalAct.QUESTION_LOCATION
        if _OBJECT_WORDS.search(text):
            return ConversationalAct.QUESTION_OBJECT
        if _PERSON_WORDS.search(text):
            return ConversationalAct.QUESTION_PERSON
        return ConversationalAct.REQUEST_INFORMATION

    if _HELP_PATTERN.search(text):
        return ConversationalAct.REQUEST_HELP
    if _INFO_REQUEST_PATTERN.search(text):
        return ConversationalAct.REQUEST_INFORMATION
    if _FAREWELL_PATTERN.search(text):
        return ConversationalAct.FAREWELL
    if _GREETING_PATTERN.search(text):
        return ConversationalAct.GREETING
    return ConversationalAct.STATEMENT
