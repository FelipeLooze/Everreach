"""Phase 24J — Conversational Relevance Validation.

The master plan's own words: "This is currently one of the highest-
priority missing guarantees." Detects when the Narrator's response
doesn't meaningfully address the CURRENT player conversational act
(Phase 24E) — the spec's own worked example: "Qual o seu nome?"
answered with "Temos uma ótima estalagem na praça." is invalid random
topic drift, never a legitimate NPC choice.

NPCs ARE allowed to lie, refuse, evade, or plead ignorance — those are
all intentional, grounded responses (spec's own list) and must NOT be
rejected here. Only genuine non-acknowledgment (no refusal marker, no
ignorance marker, no evasion marker, and no topical connection to what
was asked at all) is a violation.

Deterministic only, per the plan's explicit "avoid adding another full
LLM generation call to every normal turn merely to judge relevance" —
curated marker phrases plus keyword/proper-noun checks, the same style
already established throughout this codebase (_PERSISTENT_CONCEPTS,
_SPEECH_VERBS, narrator.py's own canon denial_pattern), not a semantic
parse or a second LLM call.

ENFORCEMENT IS DELIBERATELY NARROW (a real regression found and fixed
during this subphase, not a hypothetical): a first attempt enforced
NOT_ADDRESSED for every "must-address" act using generic keyword
overlap, and it broke a real, passing scenario — "como se chama este
lugar?" (asking a PLACE's name) answered "Isto aqui é Cardal..." shares
no literal words with the question at all (real dialogue paraphrases,
it doesn't echo the player's wording back), so the whole legitimate
answer was discarded and a village-name reveal other tests depend on
never reached persistence. Two problems compounded: (1) Phase 24E's
QUESTION_NAME bucket fires for ANY "nome"/"chama" + interrogative,
regardless of WHOSE name is being asked, and (2) literal keyword overlap
is too brittle to gate a full-response REJECTION for paraphrased
dialogue in general.

The fix: hard rejection is enforced ONLY for the unambiguous case the
spec actually worked an example for — a question that both (a)
classifies as QUESTION_NAME/QUESTION_PERSON AND (b) explicitly
references the interlocutor in second person ("seu nome", "como VOCÊ se
chama") — using the NPC's real registered name as the acceptance
signal, which is data-driven and immune to paraphrase risk (either the
NPC's actual name string appears or it doesn't). classify_relevance()
still computes a best-effort outcome across every must-address act (for
observability/trace, matching the spec's full outcome taxonomy) — but
the validator only turns NOT_ADDRESSED into a Violation for that one
narrow, high-confidence case. Broader relevance judgment for
LOCATION/OBJECT/generic-information questions is a known, deliberately
deferred gap (same spirit as Phase 24I's acknowledged organization-name
limitation), not attempted here.
"""
import re
from enum import StrEnum

from sqlalchemy.orm import Session

from app.ai.context_builder import _proper_nouns
from app.ai.conversational_act import ConversationalAct
from app.ai.conversational_act import classify as classify_conversational_act
from app.ai.narrator import _mentions, _normalized
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.game.npcs.service import _SEARCH_STOP_WORDS

# Acts with nothing mandatory to address (GREETING, STATEMENT) or their
# own dedicated grounding already (FAREWELL, Phase 24E) are out of scope.
_MUST_ADDRESS_ACTS = frozenset(
    {
        ConversationalAct.QUESTION_NAME,
        ConversationalAct.QUESTION_LOCATION,
        ConversationalAct.QUESTION_PERSON,
        ConversationalAct.QUESTION_OBJECT,
        ConversationalAct.REQUEST_INFORMATION,
        ConversationalAct.REQUEST_HELP,
    }
)
_IDENTITY_ACTS = frozenset({ConversationalAct.QUESTION_NAME, ConversationalAct.QUESTION_PERSON})


class RelevanceOutcome(StrEnum):
    ADDRESSED = "ADDRESSED"
    PARTIALLY_ADDRESSED = "PARTIALLY_ADDRESSED"
    DELIBERATELY_EVADED = "DELIBERATELY_EVADED"
    DELIBERATELY_REFUSED = "DELIBERATELY_REFUSED"
    PLAUSIBLE_IGNORANCE = "PLAUSIBLE_IGNORANCE"
    NOT_ADDRESSED = "NOT_ADDRESSED"


_REFUSAL_MARKERS = re.compile(
    r"\b(prefiro\s+nao\s+dizer|nao\s+vou\s+dizer|nao\s+posso\s+dizer|"
    r"nao\s+e\s+da\s+sua\s+conta|isso\s+nao\s+(?:te|lhe)\s+interessa|"
    r"voce\s+nao\s+precisa\s+saber|nao\s+lhe\s+diz\s+respeito)\b",
    re.IGNORECASE,
)
_IGNORANCE_MARKERS = re.compile(
    r"\b(nao\s+sei|nao\s+fac?o\s+ideia|desconhec[oe]|nao\s+tenho\s+certeza|"
    r"nao\s+saberia\s+dizer)\b",
    re.IGNORECASE,
)
_EVASION_MARKERS = re.compile(
    r"\b(prefiro\s+falar\s+sobre|isso\s+agora\s+nao\s+importa|vamos\s+deixar\s+isso|"
    r"mudemos\s+de\s+assunto|melhor\s+falarmos\s+de\s+outra\s+coisa)\b",
    re.IGNORECASE,
)
# Distinguishes "qual o SEU nome" (about the NPC) from "como se chama
# ESTE LUGAR" (about something else entirely) — both classify as
# QUESTION_NAME/QUESTION_PERSON under Phase 24E's coarser taxonomy, but
# only the former can fairly be checked against the NPC's own name.
_SELF_REFERENCE_MARKERS = re.compile(r"\b(seu|sua|voce|voces|teu|tua)\b", re.IGNORECASE)


def _is_self_identity_question(player_input: str) -> bool:
    return bool(_SELF_REFERENCE_MARKERS.search(_normalized(player_input)))


def _addresses_identity_question(response_text: str, active_npc_name: str) -> bool:
    return bool(active_npc_name) and _mentions(response_text, active_npc_name)


def _term_overlap(player_input: str, response_text: str) -> bool:
    terms = []
    for term in re.findall(r"\b\w{4,}\b", _normalized(player_input)):
        if term not in _SEARCH_STOP_WORDS and term not in terms:
            terms.append(term)
    if not terms:
        # Nothing meaningful to check overlap against (e.g. the whole
        # input was stopwords/short words) — silence, not a false
        # rejection, same principle Phase 19G already established.
        return True
    normalized_response = _normalized(response_text)
    return any(re.search(rf"\b{re.escape(term)}\w*\b", normalized_response) for term in terms)


def _gives_a_concrete_named_answer(response_text: str) -> bool:
    """Any proper noun at all (a name, place, or title) is a weak but
    real signal the NPC gave SOME specific answer rather than a vague
    non-response — used only to avoid rejecting a legitimate answer
    phrased without literally repeating the question's own words or the
    NPC's registered name (e.g. a nickname, or a place named instead)."""
    return bool(_proper_nouns(response_text))


def classify_relevance(
    player_input: str, response_text: str, active_npc_name: str = ""
) -> RelevanceOutcome:
    act = classify_conversational_act(player_input)
    if act not in _MUST_ADDRESS_ACTS:
        return RelevanceOutcome.ADDRESSED

    normalized_response = _normalized(response_text)
    if _REFUSAL_MARKERS.search(normalized_response):
        return RelevanceOutcome.DELIBERATELY_REFUSED
    if _IGNORANCE_MARKERS.search(normalized_response):
        return RelevanceOutcome.PLAUSIBLE_IGNORANCE
    if _EVASION_MARKERS.search(normalized_response):
        return RelevanceOutcome.DELIBERATELY_EVADED

    if act in _IDENTITY_ACTS and _is_self_identity_question(player_input):
        if _addresses_identity_question(response_text, active_npc_name):
            return RelevanceOutcome.ADDRESSED
        if _term_overlap(player_input, response_text) or _gives_a_concrete_named_answer(
            response_text
        ):
            return RelevanceOutcome.PARTIALLY_ADDRESSED
        return RelevanceOutcome.NOT_ADDRESSED

    # Every other must-address act: informational classification only
    # (see module docstring) — real paraphrased dialogue routinely fails
    # literal keyword overlap even when it's a perfectly good answer, so
    # this outcome is never turned into a hard rejection below.
    if _term_overlap(player_input, response_text) or _gives_a_concrete_named_answer(response_text):
        return RelevanceOutcome.ADDRESSED
    return RelevanceOutcome.NOT_ADDRESSED


_NOT_ADDRESSED_MESSAGE = (
    "a resposta não demonstra nenhum reconhecimento de que o jogador perguntou o nome/"
    "identidade do interlocutor; tópico completamente diferente sem recusa, evasão ou "
    "admissão de desconhecimento explícitas — isso é deriva de tópico, não uma escolha "
    "intencional do NPC"
)


@register_validator
def validate_conversational_relevance(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    if not proposal.text.strip() or not claims:
        return []

    act = classify_conversational_act(proposal.player_input)
    # Enforcement stays deliberately narrow — see module docstring. Only
    # a self-identity question ("qual o SEU nome") is enforced; every
    # other must-address act is intentionally left unenforced here.
    if act not in _IDENTITY_ACTS or not _is_self_identity_question(proposal.player_input):
        return []

    outcome = classify_relevance(
        proposal.player_input, proposal.text, proposal.active_npc_name or ""
    )
    if outcome != RelevanceOutcome.NOT_ADDRESSED:
        return []

    # The whole response is off-topic, not just one sentence — every
    # claim index is marked so contract.py's repair drops the entire
    # text (falls under MIN_COHERENT_REPAIR_CHARS) rather than keeping
    # unrelated sentences the earlier claim was attached to.
    return [
        Violation(claim_index=claim.index, category=ClaimCategory.AUTHORITATIVE, reason=_NOT_ADDRESSED_MESSAGE)
        for claim in claims
    ]
