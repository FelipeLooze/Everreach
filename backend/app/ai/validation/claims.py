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

from app.ai.narrator import (
    _mentions,
    _normalized,
    _paragraph_has_spoken_dialogue,
    _protagonist_agency_violations,
    _split_paragraphs,
    _split_sentences,
)


class ClaimCategory(StrEnum):
    DECORATIVE = "DECORATIVE"
    SENSORY = "SENSORY"
    PERCEPTUAL = "PERCEPTUAL"
    AUTHORITATIVE = "AUTHORITATIVE"
    MECHANICAL = "MECHANICAL"
    PLAYER_VOLUNTARY = "PLAYER_VOLUNTARY"
    PERSISTENT_CANON = "PERSISTENT_CANON"
    # Phase 24G — reuses narrator.py's own _paragraph_has_spoken_dialogue
    # (dash-led, colon-attributed, and quote-mark shapes) instead of a
    # second, narrower per-validator heuristic. Concrete gap this closed:
    # app.ai.validation.knowledge's own dialogue check only recognized a
    # leading dash, silently missing the colon-attributed and quote-mark
    # dialogue shapes narrator.py itself already treats as spoken.
    NPC_DIALOGUE = "NPC_DIALOGUE"


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
    # Phase 24I — irma[oo] never matched "irmão"/"irmãos" (needed a
    # literal "irma"+"o", but consuming the alternation's single char
    # left no room for the second "o" before the word boundary); and
    # organizaca?[oa] never matched "organização"/"organizações" at all
    # (see the identical, independently-discovered bug in narrator.py's
    # _PERSISTENT_CONCEPTS, fixed the same way there).
    r"filh[oa]|irm(?:a|ao|as|aos)|esposa|marido|namorad[oa]|amante|segredo\w*|"
    r"organizac(?:ao|oes)|guilda|taverna|loja|vila|cidade|templo|"
    r"casad[oa]|noiv[oa]"
    r")\b",
    re.IGNORECASE,
)

_MECHANICAL_KEYWORDS = re.compile(
    r"\b(golpe|ataque|acerta\w*|erra\w*|fere\w*|derrota\w*|"
    r"morre\w*|cai\w*|arremessa\w*|derruba\w*|quebra\w*)\b",
    re.IGNORECASE,
)

# Phase 19E — SENSATION != EMOTION. Unlike PLAYER_VOLUNTARY's subject-
# position check above (which only catches "Logan decide/sente X"),
# an interpreted emotional conclusion is invalid regardless of grammar
# — the spec's own invalid example "Terror fills you" puts the
# protagonist as the OBJECT, not the subject. Matching this keyword
# list anywhere the protagonist is mentioned (not just as subject)
# closes that gap without needing real subject/object parsing.
_INTERPRETED_EMOTION_KEYWORDS = re.compile(
    r"\b("
    r"medo|terror|panico|apavorad[oa]s?|assustad[oa]s?|"
    r"felicidade|feliz(?:es)?|alegria|alegre[s]?|"
    r"tristeza|trist[eo]s?|"
    r"raiva|zangad[oa]s?|irritad[oa]s?|"
    r"alivio|aliviad[oa]s?|"
    r"atracao|atraid[oa]s?|"
    r"desejo|desejand[oa]|"
    r"nojo|repulsa|enojad[oa]s?|"
    r"odio|odeia\w*|"
    r"curiosidade"
    r")\b",
    re.IGNORECASE,
)


_CLAUSE_SEPARATORS = re.compile(r",| e | mas | ou | porem | contudo | entretanto |;")


def _has_same_clause_emotion_claim(text: str, character_name: str) -> bool:
    name_token = re.escape(_normalized(character_name).split()[0])
    for clause in _CLAUSE_SEPARATORS.split(_normalized(text)):
        if re.search(rf"\b{name_token}\b", clause) and _INTERPRETED_EMOTION_KEYWORDS.search(clause):
            return True
    return False


def split_into_claims(text: str) -> list[str]:
    return _split_sentences(text)


def classify_claim(
    text: str,
    *,
    character_name: str = "",
    known_names: tuple[str, ...] = (),
    dialogue_context: bool | None = None,
) -> frozenset[ClaimCategory]:
    """dialogue_context (Phase 24H): whether `text`'s PARENT PARAGRAPH is
    spoken dialogue, when the caller already knows this. extract_claims
    passes it explicitly because a dash-led paragraph's later sentences
    don't repeat the dash — a single sentence checked in isolation can't
    always tell it's still inside dialogue on its own. None (the default,
    used by direct callers/tests passing an already-isolated sentence)
    falls back to auto-detecting from `text` itself, same as before this
    parameter existed."""
    categories: set[ClaimCategory] = set()
    normalized_text = _normalized(text)

    if _SENSORY_KEYWORDS.search(normalized_text):
        categories.add(ClaimCategory.SENSORY)

    is_dialogue = _paragraph_has_spoken_dialogue(text) if dialogue_context is None else dialogue_context

    # Reuses app.ai.narrator's own careful subject-position detection
    # (object-preposition exclusion, etc.) instead of a second, weaker
    # "mentions the name anywhere + a voluntary verb anywhere" heuristic
    # — "Osgar sorri para Logan" must not classify as PLAYER_VOLUNTARY
    # just because Logan is named as the object, not the subject.
    if character_name and _protagonist_agency_violations(
        text, character_name, dialogue_context=is_dialogue
    ):
        categories.add(ClaimCategory.PLAYER_VOLUNTARY)

    # Phase 19E — catches "Terror fills you"-shaped claims the check
    # above misses (protagonist as object, not subject of the verb).
    # Clause-scoped (not "anywhere in the sentence"): "Osgar sente
    # alívio e sorri ao ver Logan chegar" must not flag just because
    # Logan is named in a LATER clause than Osgar's own emotion.
    if character_name and _has_same_clause_emotion_claim(text, character_name):
        categories.add(ClaimCategory.PLAYER_VOLUNTARY)

    if _PERSISTENT_ENTITY_KEYWORDS.search(normalized_text):
        categories.add(ClaimCategory.PERSISTENT_CANON)

    if _MECHANICAL_KEYWORDS.search(normalized_text):
        categories.add(ClaimCategory.MECHANICAL)

    if any(name and _mentions(text, name) for name in known_names):
        categories.add(ClaimCategory.AUTHORITATIVE)

    if is_dialogue:
        categories.add(ClaimCategory.NPC_DIALOGUE)

    if not categories:
        categories.add(ClaimCategory.DECORATIVE)

    return frozenset(categories)


def extract_claims(
    text: str,
    *,
    character_name: str = "",
    known_names: tuple[str, ...] = (),
) -> list[NarrativeClaim]:
    """Phase 24H — iterates paragraphs (not the flat sentence list
    split_into_claims would give directly) so each sentence's classification
    can be told whether ITS PARAGRAPH is dialogue, computed once from the
    whole paragraph rather than re-derived from a single sentence that may
    have lost the paragraph's own leading dash. Sentence content and global
    ordering are unchanged from the flat approach — this only threads
    dialogue_context through, it doesn't change what text becomes a claim."""
    claims: list[NarrativeClaim] = []
    index = 0
    for paragraph in _split_paragraphs(text):
        paragraph_is_dialogue = _paragraph_has_spoken_dialogue(paragraph)
        for sentence in split_into_claims(paragraph):
            claims.append(
                NarrativeClaim(
                    index=index,
                    text=sentence,
                    categories=classify_claim(
                        sentence,
                        character_name=character_name,
                        known_names=known_names,
                        dialogue_context=paragraph_is_dialogue,
                    ),
                )
            )
            index += 1
    return claims
