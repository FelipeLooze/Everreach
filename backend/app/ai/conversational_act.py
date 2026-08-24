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
    r"\bloja\b|\bcomprar\b|\bvender\b|\btaverna\b|\bestalagem\b|\bpre[çc]o\b|\bhospedagem\b|\bquarto\b",
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
