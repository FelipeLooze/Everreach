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
