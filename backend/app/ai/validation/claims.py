"""Phase 19B/19C — Narrative Claim Extraction & Classification.

Claims are extracted at SENTENCE granularity, reusing app.ai.narrator's
own sentence splitter (_split_sentences) rather than a second regex —
narrator.py's own repair functions (_drop_agency_violations,
_drop_unsupported_segments, ...) already operate at this exact
granularity, so a validator built on top of the same units can never
disagree with narrator.py about what one droppable claim is.

Classification is deterministic keyword/pattern matching, not an LLM
call and not a full NLP parse ("LLM extraction is not validation" —
spec). A claim may carry more than one category (the spec's own
example: "Logan feels the freezing wind and decides to return" is both
SENSORY and PLAYER_VOLUNTARY); DECORATIVE is the default when nothing
else matches, never an error state.
"""
import re
from dataclasses import dataclass
from enum import StrEnum

from app.ai.narrator import _mentions, _normalized, _protagonist_agency_violations, _split_sentences


class ClaimCategory(StrEnum):
    DECORATIVE = "DECORATIVE"
    SENSORY = "SENSORY"
    PERCEPTUAL = "PERCEPTUAL"
    AUTHORITATIVE = "AUTHORITATIVE"
    MECHANICAL = "MECHANICAL"
    PLAYER_VOLUNTARY = "PLAYER_VOLUNTARY"
    PERSISTENT_CANON = "PERSISTENT_CANON"


@dataclass(frozen=True)
class NarrativeClaim:
    index: int
    text: str
    categories: frozenset[ClaimCategory]

    def is_(self, category: ClaimCategory) -> bool:
        return category in self.categories


# Phase 19E — Sensory & Physiological Narration Policy. Deliberately
# broad: thermal, touch, smell, hearing, taste, pain/discomfort, and
# involuntary physiological response, exactly the categories the spec
# enumerates as always-allowed narrative texture.
_SENSORY_KEYWORDS = re.compile(
    r"\b("
    r"fri[oa]s?|gelad[oa]s?|calor|quente|quentes|arrepia?[m]?|arrepio\w*|"
    r"cheir[oa]s?|arom[ao]s?|fedor|fedid[oa]s?|"
    r"sabor\w*|gost[oa]s?|amarg[oa]s?|doce[s]?|metalic[oa]s?|"
    r"som|sons|barulh[oa]s?|eco|ecoa\w*|ruid[oa]s?|silencio|zumbid[oa]s?|"
    r"dor|dores|doi|doem|ard[oe][r]?\w*|"
    r"cansac[oa]s?|cansad[oa]s?|fadiga|exaust[oa]s?|"
    r"coracao|batid[ao]s?|respiraca?[oa]\w*|respira\w*|folego|"
    r"su[ao]r\w*|suando|"
    r"tremor|treme[m]?|tremend[oa]s?|estremec\w*|"
    r"umidade|umid[oa]s?|molhad[oa]s?|"
    r"textura|asper[oa]s?|lis[oa]s?|rugos[oa]s?|"
    r"pes[oa]s?|pesad[oa]s?|"
    r"vento|brisa|pele|tato|toque|"
    r"tontura|tont[oa]s?|nause[a]?|enjo[oa]\w*|formigament[oa]"
    r")\b",
    re.IGNORECASE,
)

_PERSISTENT_ENTITY_KEYWORDS = re.compile(
    r"\b("
    r"filh[oa]|irma[oo]|esposa|marido|namorad[oa]|amante|segredo\w*|"
    r"organizaca?[oa]|guilda|taverna|loja|vila|cidade|templo|"
    r"casad[oa]|noiv[oa]"
    r")\b",
    re.IGNORECASE,
)

_MECHANICAL_KEYWORDS = re.compile(
    r"\b(golpe|ataque|acerta\w*|erra\w*|fere\w*|derrota\w*|"
    r"morre\w*|cai\w*|arremessa\w*|derruba\w*|quebra\w*)\b",
    re.IGNORECASE,
)


def split_into_claims(text: str) -> list[str]:
    return _split_sentences(text)


def classify_claim(
    text: str,
    *,
    character_name: str = "",
    known_names: tuple[str, ...] = (),
) -> frozenset[ClaimCategory]:
    categories: set[ClaimCategory] = set()
    normalized_text = _normalized(text)

    if _SENSORY_KEYWORDS.search(normalized_text):
        categories.add(ClaimCategory.SENSORY)

    # Reuses app.ai.narrator's own careful subject-position detection
    # (object-preposition exclusion, etc.) instead of a second, weaker
    # "mentions the name anywhere + a voluntary verb anywhere" heuristic
    # — "Osgar sorri para Logan" must not classify as PLAYER_VOLUNTARY
    # just because Logan is named as the object, not the subject.
    if character_name and _protagonist_agency_violations(text, character_name):
        categories.add(ClaimCategory.PLAYER_VOLUNTARY)

    if _PERSISTENT_ENTITY_KEYWORDS.search(normalized_text):
        categories.add(ClaimCategory.PERSISTENT_CANON)

    if _MECHANICAL_KEYWORDS.search(normalized_text):
        categories.add(ClaimCategory.MECHANICAL)

    if any(name and _mentions(text, name) for name in known_names):
        categories.add(ClaimCategory.AUTHORITATIVE)

    if not categories:
        categories.add(ClaimCategory.DECORATIVE)

    return frozenset(categories)


def extract_claims(
    text: str,
    *,
    character_name: str = "",
    known_names: tuple[str, ...] = (),
) -> list[NarrativeClaim]:
    return [
        NarrativeClaim(
            index=index,
            text=sentence,
            categories=classify_claim(
                sentence, character_name=character_name, known_names=known_names
            ),
        )
        for index, sentence in enumerate(split_into_claims(text))
    ]
