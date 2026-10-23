import difflib
from enum import StrEnum
from pathlib import Path
import re
from typing import Literal, NamedTuple
import unicodedata

from app.ai.conversational_act import (
    QUESTION_ACTS,
    ConversationalAct,
    _SERVICE_WORDS,
    classify as classify_conversational_act,
    is_price_question,
)
from app.ai.llm_call import call_llm
from app.ai.llm_service import LLMService
from app.core.enums import CONNECTION_TYPE_LABELS_PT
from app.core.logging import get_logger
from app.game.world.content_pools import SETTLEMENT_SERVICE_POOL

logger = get_logger("narration")


# Phase 24L — Repair/Regeneration Pipeline. The spec's own named failure
# classes ("different failure classes should communicate precise repair
# reasons"). Not every category has a producer inside narrator.py's own
# pipeline today (RELEVANCE is Phase 24J's separate post-hoc validator,
# which runs after narrate() already returned and logs its own trace —
# out of scope here) — the taxonomy still names it so a future producer
# has a home to log into rather than inventing a seventh ad-hoc label.
class RepairReasonCategory(StrEnum):
    PLAYER_AGENCY = "PLAYER_AGENCY"
    NPC_IDENTITY = "NPC_IDENTITY"
    CANON = "CANON"
    KNOWLEDGE = "KNOWLEDGE"
    RELEVANCE = "RELEVANCE"
    FORMAT = "FORMAT"


class NarrationOutcome(StrEnum):
    MANUAL_REVIEW = "MANUAL_REVIEW"
    ACCEPTED_FIRST_PASS = "ACCEPTED_FIRST_PASS"
    ACCEPTED_AFTER_REVISION = "ACCEPTED_AFTER_REVISION"
    REPAIRED_VIA_TRIM = "REPAIRED_VIA_TRIM"
    FALLBACK = "FALLBACK"


def _log_narration_outcome(
    outcome: NarrationOutcome,
    *,
    attempt: int,
    category: RepairReasonCategory | None = None,
    reason: str = "",
) -> None:
    """One consistent, always-on (INFO, not DEBUG) line per narrate() call
    — the spec's own "measure: first-pass acceptance rate, repair rate,
    fallback rate" ask is otherwise only answerable by grepping several
    differently-shaped FALLBACK REASON/FINAL RESPONSE log messages. This
    doesn't compute the rates itself (no metrics backend exists here to
    aggregate into) — it makes them computable from ordinary logs without
    needing DEBUG verbosity, matching the spec's "prefer lightweight"
    guidance over building real metrics infrastructure for this alone.
    """
    logger.info(
        "NARRATION OUTCOME: %s attempt=%s category=%s reason=%s",
        outcome.value,
        attempt,
        category.value if category is not None else "NONE",
        reason or "-",
    )

_PROMPT_PATH = Path(__file__).parent / "prompts" / "narrator_system.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# Phase 24K — the Phase 24A.1 audit's own finding: ~225 lines (~15% of
# the prompt) were OPENING-only instructions ("PRIMEIRA CHEGADA" through
# "FINAL DA ABERTURA" — first-arrival cinematics, darkness/sound,
# transport/appearance, other transported people, natives during first
# arrival, the interface, ending the opening) sent on every single
# CONTINUATION turn, where none of it is ever relevant. Split out of
# narrator_system.txt (which is now the CONTINUATION-applicable base)
# into its own file, appended only when mode == "OPENING". Splitting
# instead of a runtime string-search/strip keeps this a single, cheap
# file read at import time — no per-turn parsing cost.
_OPENING_PROMPT_PATH = Path(__file__).parent / "prompts" / "narrator_system_opening.txt"
_OPENING_SYSTEM_PROMPT_SUFFIX = "\n\n" + _OPENING_PROMPT_PATH.read_text(encoding="utf-8")

NarrationMode = Literal["OPENING", "CONTINUATION"]


def _system_prompt_for(mode: NarrationMode) -> str:
    if mode == "OPENING":
        return _SYSTEM_PROMPT + _OPENING_SYSTEM_PROMPT_SUFFIX
    return _SYSTEM_PROMPT

_OPENING_ALLOWED_SUBJECT_VERBS = {
    "esta",
    "encontra",
    "surge",
    "aparece",
    "materializa",
}

# Phase 24J.2 — sensory/perceptual verbs, allowed as the protagonist's own
# grammatical subject in ANY mode (not just OPENING). This mirrors a
# policy _protagonist_agency_violations' own mental_state_pattern already
# established (its docstring: "Deliberately excludes percebe/nota...
# legitimately sensory/perceptual... SENSATION != EMOTION policy (19E)")
# but subject_pattern below never shared it — confirmed via live trace as
# a real regression: a plain EXAMINE action ("Olhar ao redor"), whose own
# mechanical summary literally starts "Logan observa os arredores de
# X...", produced narration opening the same natural way ("Logan observa
# a praça...") and was rejected as a player-agency violation on that
# basis alone, falling all the way to "Nada acontece de imediato." for
# what both the narrator AND its own inputs consider proper, non-agentive
# scene description.
_SENSORY_PERCEPTION_VERBS = {
    "observa",
    "nota",
    "percebe",
    "repara",
    "ve",
    "avista",
    "ouve",
    "escuta",
}

# Phase 24J.5 — Issue 3. Confirmed via live trace (req=nr_edfafd53ef72): a
# bare "olhar ao redor" — the same authorized EXAMINE action the sensory
# set above exists for — got narrated as "Logan DÁ uma última volta de
# olhos pela vila, avaliando seus arredores..." and was rejected across
# both revision attempts because "dá" isn't in _SENSORY_PERCEPTION_VERBS.
# Rather than keep growing that set unconditionally (the spec's own
# architectural question: is the agency guard becoming dependent on an
# ever-longer verb allowlist?), these verbs are legitimate ONLY when this
# turn's own AUTHORITATIVE mechanical fact confirms the backend actually
# resolved an observation action — narrate()'s existing mechanical_summary
# parameter already carries that signal (_handle_examine's own summary
# always starts "{name} observa os arredores..."), so no new engine.py
# plumbing was needed to check it. Unlike _SENSORY_PERCEPTION_VERBS (always
# safe, any mode, any turn — genuinely passive perception verbs by nature),
# this set is intentionally gated: "examina"/"avalia" could plausibly
# introduce a fabricated OBJECT if allowed unconditionally, so they only
# bypass the guard when the backend itself already authorized this exact
# turn as an observation.
_OBSERVATION_FRAMING_VERBS = {
    "da",
    "lanca",
    "examina",
    "inspeciona",
    "contempla",
    "avalia",
    "estuda",
}

_OBSERVATION_TURN_PATTERN = re.compile(r"\bobserva\s+os\s+arredores\b")

# Phase 24J.3 — movement-completion verbs, allowed as the protagonist's own
# grammatical subject in ANY mode, mirroring the sensory-verb exception
# above: narrating a MOVE action's own authoritative destination (e.g.
# "Logan caminha... até chegar à Estalagem de Belridge") necessarily makes
# the protagonist the grammatical subject of a movement verb, but describes
# an ALREADY-DECIDED, backend-authoritative fact (travel_service.move_character
# already ran and character.location_id already changed) rather than an
# invented new decision. Without this exception every successfully-resolved
# MOVE/arrival/entry action fell straight to the generic agency-violation
# fallback ("Nada acontece de imediato.") — confirmed via live trace
# (req=nr_57c43a314ed6 and five further consecutive MOVE-resolved turns in
# the same playtest session) even though character.location_id had already,
# correctly, changed.
_MOVEMENT_RESULT_VERBS = {
    "caminha",
    "chega",
    "entra",
    "sai",
    "afasta",
    "despede",
    "parte",
    "segue",
    "anda",
    "viaja",
    "volta",
    "retorna",
    "atravessa",
    "avanca",
    "aproxima",
    "dirige",
}

_FORBIDDEN_STYLE_MARKERS = (
    "como se",
    "o ar parece",
    "o silêncio parece",
    "a sombra se alonga",
)

# Prepositions that put the protagonist's name in OBJECT position ("Osgar olhou
# para Logan"). Object position is fine — the world/NPC is still the subject.
_OBJECT_PREPOSITIONS = r"(?:para|a|ao|à|com|de|do|da|sobre|junto a)"

# Vocabulary that reveals awareness of being inside a game. NPCs believe the
# world is real and must never use these terms — only the narrator/system
# voice (outside NPC dialogue) may name the game or describe it as a game.
_META_GAME_TERMS = re.compile(
    r"\b(?:vrmmorpg|vrmmo|logout|login|servidor|npc)\b|"
    r"\bsincroniza(?:cao|ção)\w*\b|"
    r"\b(?:sou|somos|sao|são)\s+(?:um\s+|uns\s+)?jogador(?:es)?\b",
    re.IGNORECASE,
)

# Verbs of speech that, followed by the protagonist's name, mean the narrator
# invented a NEW line of dialogue and attributed it to the protagonist.
_SPEECH_VERBS = (
    r"diz|disse|dizem|responde|respondeu|pergunta|perguntou|sussurra|sussurrou|"
    r"grita|gritou|exclama|exclamou|murmura|murmurou|resmunga|resmungou"
)

# Verbs describing an NPC/world reaction TO a decision already made — these
# presuppose the protagonist already replied, even when the reply itself never
# named them (e.g. an unattributed "— ..." line the narrator wrote and then
# treated as settled). Catches fabricated turns the name-based checks below miss.
_REACTS_TO_DECISION_VERBS = (
    r"respeita|aceita|concorda\s+com|reage\s+(?:a|à)|atende\s+(?:a|ao)|"
    r"acena\s+(?:a|para)|entende|compreende"
)
_DECISION_NOUNS = r"desejo|decis(?:ao|ão)|resposta|escolha|pedido|vontade"

_PERSISTENT_CONCEPTS = {
    "casa": r"\bcasas?\b",
    "madeira": r"\bmadeira\b",
    "sapé": r"\bsape\b",
    "ferramenta": r"\bferramentas?\b",
    "artesanato": r"\bartesanato\b",
    "recursos naturais": r"\brecursos?\s+naturais\b",
    "profissões locais": r"\b(fazendeir\w*|mineir\w*|artesaos?|artesa)\b",
    "animais selvagens": r"\banimais?\s+selvagens?\b",
    "segurança de rota": r"\b(segur[oa]s?|perigos[oa]s?)\b",
    "trilha": r"\btrilhas?\b",
    "estrada": r"\bestradas?\b",
    "ponte": r"\bpontes?\b",
    "rio": r"\brios?\b",
    "riacho": r"\briachos?\b",
    "lago": r"\blagos?\b",
    "montanha": r"\bmontanhas?\b",
    "colina": r"\bcolinas?\b",
    "planície": r"\bplanicies?\b",
    "floresta": r"\bflorestas?\b",
    "bosque": r"\bbosques?\b",
    "templo": r"\btemplos?\b",
    "igreja": r"\bigrejas?\b",
    "capela": r"\bcapelas?\b",
    "guilda": r"\bguildas?\b",
    "castelo": r"\bcastelos?\b",
    "loja": r"\blojas?\b",
    "taverna": r"\btavernas?\b",
    # Phase 24I — was r"\bestalagens?\b" ("estalagen" + optional final
    # "s"), which never matches the actual singular word "estalagem"
    # (ends in "-gem", not "-gens"); only the plural "estalagens" ever
    # matched. Confirmed via the spec's own "minha estalagem" example
    # silently passing validation.
    "estalagem": r"\bestalage(?:m|ns)\b",
    "cidade": r"\bcidades?\b",
    "vila": r"\bvilas?\b",
    "ruína": r"\bruinas?\b",
    "masmorra": r"\b(masmorras?|dungeons?)\b",
    # Phase 24I — generic structures/institutions the spec's own examples
    # named ("o prédio do conselho") that nothing previously covered.
    "prédio": r"\b(predios?|edificios?)\b",
    "conselho": r"\bconselhos?\b",
    "facção": r"\bfacc(?:ao|oes)\b",
    # Phase 24I — "organização"/"grupo" as generic category words,
    # matching the existing guilda/facção pattern: catches narration
    # inventing "a organização X"/"o grupo Y" even when it doesn't use
    # one of the more specific category words above. A wholly invented
    # proper name with no category noun at all (no "guilda"/"facção"/
    # "organização"/"grupo" anywhere) is a known, harder gap this
    # keyword-based mechanism cannot close without risking false
    # positives on ordinary capitalized names — left for a future
    # phase, not attempted here.
    "organização": r"\borganizac(?:ao|oes)\b",
    "grupo": r"\bgrupos?\b",
    "religião": r"\breligi(?:ao|oes)\b",
    "prática religiosa": r"\b(fe|religios[oa]s?|cult\w*|rez\w*|sacerd\w*|orac\w*)\b",
    "história inventada": r"\b(antepassad\w*|ancestr\w*)\b",
    "divindade": r"\b(deuses?|divindades?)\b",
    "dragão": r"\bdragoes?\b",
    "guerra": r"\bguerras?\b",
    "desastre": r"\bdesastres?\b",
    "norte": r"\bnorte\b",
    "sul": r"\bsul\b",
    "leste": r"\bleste\b",
    "oeste": r"\boeste\b",
    # Phase 24I — unsupported family relationships (spec's own required
    # example). Reuses the same word set claims.py's
    # _PERSISTENT_ENTITY_KEYWORDS already names for claim classification,
    # but written correctly this time (see the irmã/irmão fix below) —
    # this dict is the one that actually gates narration, unlike the
    # claims.py list, which only affects a claim's CATEGORY label.
    "filho(a)": r"\bfilh[oa]s?\b",
    "irmão/irmã": r"\birm(?:a|ao|as|aos)\b",
    "cônjuge": r"\b(esposas?|esposos?|marido\w*)\b",
    "namorado(a)": r"\bnamorad[oa]s?\b",
    "segredo": r"\bsegredos?\b",
}

_UNSOLICITED_OPENING_INTERACTION_MESSAGE = (
    "a abertura iniciou diálogo ou aproximação de um habitante sem uma interação "
    "ativa autorizada; apresente apenas a situação inicial e devolva o controle ao jogador"
)
_HIDDEN_NAME_MESSAGE = (
    "a resposta revelou um nome canônico que o protagonista ainda não conhece e que "
    "nenhum interlocutor ativo estava autorizado a comunicar"
)


_PROMPT_LEAK_MARKERS = (
    "HARD VIOLATIONS TO REMOVE",
    "VIOLATIONS TO REMOVE",
    "DRAFT TO REVISE",
    "SCENE CONTEXT:",
    "RECENT HISTORY:",
    "PLAYER INPUT:",
    "AUTHORITATIVE MECHANICAL FACTS:",
    "MODO DA CENA:",
    "Reescreva somente a narrativa corrigida",
    "Escreva somente o próximo momento da cena",
    "REGENERAÇÃO SOLICITADA PELO JOGADOR",
    "RASCUNHO ANTERIOR:",
    "FEEDBACK DO JOGADOR",
    # Not a literal prompt echo — the model regressing into simulating a
    # whole future exchange itself, inventing several more player/NPC
    # turns nobody asked for, labeled with its own shorthand for the
    # "PLAYER INPUT:"/narrator-response shape it has seen in the prompt.
    # Just as unacceptable as an echoed instruction: everything from the
    # first such label onward is fabricated, unauthorized turns.
    "PLAYER:",
    "NARRATOR:",
    # Phase 24A.1 — the new bounded history/current-turn framing's own
    # literal headers/footers. If the model ever echoes one of these
    # back, that is unambiguously leaked scaffolding, never real prose.
    "HISTÓRICO DE TROCAS RECENTES",
    "FIM DO HISTÓRICO DE TROCAS RECENTES",
    "TURNO ATUAL DO JOGADOR",
    "FIM DO TURNO ATUAL DO JOGADOR",
)


def _strip_prompt_leak(text: str) -> str:
    """If the model echoed part of its own prompt/instructions instead of (or
    appended to) actual narrative, cut everything from the first leaked marker
    onward. Under a long revision prompt, a local model sometimes regresses to
    parroting its input verbatim — that scaffolding text must never reach the
    player, even when it contains no canon/agency violation on its own."""
    earliest = len(text)
    for marker in _PROMPT_LEAK_MARKERS:
        index = text.find(marker)
        if index != -1:
            earliest = min(earliest, index)
    return text[:earliest].strip()


_EMPTY_OR_LEAKED_RESPONSE_MESSAGE = (
    "a resposta ficou vazia depois de remover texto de instrução/prompt ecoado pelo "
    "modelo; escreva somente a cena em português, nunca repita estas instruções"
)

# Phase 24J.3 — the base model occasionally leaks its own raw internal
# reasoning, in Chinese, directly into player-facing output (observed
# repeatedly in live playtests: req from this phase's own validation runs,
# and a single earlier instance noted in the 24J.1 report). Portuguese
# narration should never legitimately contain CJK Unified Ideographs, so
# this is a safe, unambiguous signal to force a retry — gated through the
# SAME early short-circuit as an empty response, since a leak this severe
# makes every downstream check on the draft meaningless.
_CJK_SCRIPT_PATTERN = re.compile(r"[一-鿿]")

_NON_PORTUGUESE_SCRIPT_MESSAGE = (
    "a resposta contém caracteres de escrita CJK (provavelmente raciocínio interno do "
    "modelo vazando para a saída); escreva somente a cena em português"
)

# Phase 24K — the same class of leak the CJK check above already
# catches, in a Latin-alphabet shape a script check cannot see: a
# stronger remote model (nvidia/nemotron-3-ultra-550b-a55b:free via
# OpenRouter) confirmed LIVE to occasionally return its own raw
# English chain-of-thought as the entire response ("The user is
# asking me to write the next narrative moment. Let me analyze the
# context carefully...") — sending OpenRouter's own documented
# reasoning.exclude request parameter (app.ai.llm_service.
# OpenRouterLLMService) reduced but did not eliminate this for this
# specific free-tier model/route.
#
# A diacritic-DENSITY heuristic was tried first and reverted: it false-
# positived on multiple pre-existing, legitimate, all-Portuguese test
# fixtures (short exchanges using mostly unaccented common words, e.g.
# "— Osgar sorri e acena com a cabeça." / "— O que posso fazer por
# aqui?") — real Portuguese prose can easily run long stretches with
# few or no accented words, so ratio alone is not a safe signal.
#
# The word "the" is the fix: it is one of the most common words in
# English and has no Portuguese cognate — it cannot appear in
# legitimate narration by coincidence, no matter how unaccented that
# narration's own words happen to be. Every real leaked sample
# (this session's own live evidence) uses it 5+ times ("The user...",
# "the context...", "the previous turn...", "the AUTHORITATIVE...");
# every one of the test fixtures that broke the diacritic version uses
# it zero times. A minimum repeat count (not just >=1) keeps this safe
# even against a single incidental false match this reasoning hasn't
# anticipated.
_ENGLISH_ARTICLE_PATTERN = re.compile(r"\bthe\b", re.IGNORECASE)
_ENGLISH_LEAK_MIN_THE_COUNT = 3

_ENGLISH_REASONING_LEAK_MESSAGE = (
    "a resposta parece ser texto em inglês descrevendo o raciocínio do modelo sobre a "
    "tarefa, não a cena narrada (usa a palavra inglesa 'the' repetidamente, o que nunca "
    "ocorre em português); escreva somente a cena em português, nunca análise da instrução"
)


def _looks_like_english_reasoning_leak(text: str) -> bool:
    return len(_ENGLISH_ARTICLE_PATTERN.findall(text)) >= _ENGLISH_LEAK_MIN_THE_COUNT


def _empty_response_violations(text: str) -> list[str]:
    if not text.strip():
        return [_EMPTY_OR_LEAKED_RESPONSE_MESSAGE]
    if _CJK_SCRIPT_PATTERN.search(text):
        return [_NON_PORTUGUESE_SCRIPT_MESSAGE]
    if _looks_like_english_reasoning_leak(text):
        return [_ENGLISH_REASONING_LEAK_MESSAGE]
    return []


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _authoritative_context_only(context: str) -> str:
    """Exclude the player's untrusted claim audit from the canon allow-list."""
    before_audit, marker, after_audit = context.partition("PLAYER INPUT CANON CHECK")
    if not marker:
        return context
    _audit, next_marker, authoritative_tail = after_audit.partition("\n\nACTIVE QUESTS")
    if not next_marker:
        return before_audit
    return f"{before_audit}\n\nACTIVE QUESTS{authoritative_tail}"


# Phase 24J.4 — Issue 1 (Relational Geography Hallucination). Confirmed via
# live trace, 3 separate campaigns: the OLD route_kind+direction check below
# only asks "does this vocabulary combination exist ANYWHERE in context?" —
# it never asks WHICH destination the combination is actually about. A real
# route (village -[ROAD,east]-> Estrada do Moinho) and a real but UNRELATED
# route (village -[PATH,south]-> the inn) each individually satisfy that
# check, so the model could freely claim "the inn is east, near Estrada do
# Moinho" and nothing caught it — both individual facts exist; their
# COMBINATION does not. Fixed by correlating each direction/route-kind
# mention to the NEAREST known-destination mention in the same sentence,
# then checking that pairing against the specific LocationConnection for
# THAT destination — never against "does this exist somewhere."
_DIRECTION_WORDS_PT = (
    "nordeste", "noroeste", "sudeste", "sudoeste",
    "norte", "sul", "leste", "oeste",
)
_ROUTE_KIND_WORDS_PT = tuple(sorted(set(CONNECTION_TYPE_LABELS_PT.values())))

# Longest-label-first so a multi-word service label ("quadro de avisos")
# is matched whole rather than partially by a shorter overlapping prefix.
_SETTLEMENT_SERVICE_LABELS_PT = tuple(
    sorted(
        {_normalized(label) for label, _type, _description in SETTLEMENT_SERVICE_POOL.values()},
        key=len,
        reverse=True,
    )
)


class _KnownConnection(NamedTuple):
    direction: str
    destination_name: str
    route_kind: str
    type_alias: str | None


_KNOWN_CONNECTION_LINE_PATTERN = re.compile(
    r"^-\s*(?P<direction>\S+)\s*->\s*(?P<destination>.+?)"
    r"(?:\s*\[(?P<type_label>[^\[\]]+)\])?\s*\((?P<route_kind>[^,]+),"
)


def _parse_known_connections(context: str) -> list[_KnownConnection]:
    """Parse the SAME structured per-destination connection facts already
    exposed to the narrator (context_builder._known_connection_lines) back
    into a comparable form — the established codebase pattern (see
    _extract_character_name, _private_location_fields) rather than a new
    parallel channel. "Preserve entity relationship": each line is already
    exactly one (direction, destination, route_kind, type) tuple; this
    never flattens them into an unrelated bag of words.

    A destination whose proper NOUN is still hidden ("Local desconhecido")
    is still kept, not discarded — its TYPE (in square brackets, when
    recognized) stays visible even before the name does, mirroring the
    established "Type is DIRECTLY PERCEPTIBLE, Name may be HIDDEN"
    distinction CANONICAL LOCATION CONTEXT already draws. Confirmed via
    live trace as a real gap: an early-game existence/direction question
    ("existe uma estalagem? onde fica?") is answered before the player
    has been taught ANY destination's proper name, so every entry
    redacted to "Local desconhecido" and this validator had zero ground
    truth to correlate against — even though the structural fact (this
    connection leads to an inn) was never actually secret.
    """
    section_match = re.search(
        r"CONNECTED LOCATIONS KNOWN TO PLAYER\n(.*?)(?:\n\n|\Z)", context, re.DOTALL
    )
    if not section_match:
        return []
    connections = []
    for line in section_match.group(1).splitlines():
        match = _KNOWN_CONNECTION_LINE_PATTERN.match(line.strip())
        if not match:
            continue
        destination = match.group("destination").strip()
        type_label = match.group("type_label")
        connections.append(
            _KnownConnection(
                direction=_normalized(match.group("direction")),
                destination_name=destination,
                route_kind=_normalized(match.group("route_kind")),
                type_alias=_normalized(type_label) if type_label else None,
            )
        )
    return connections


def _service_alias_for(connection: _KnownConnection) -> str | None:
    """The generic Portuguese label a player would naturally use for this
    destination ("estalagem") — from its own context-supplied type label
    when the proper noun is still hidden, otherwise derived from the
    known name itself (a settlement service is always named '{Label} de
    {village}' at world-gen time). Reuses SETTLEMENT_SERVICE_POOL as the
    single source of truth rather than a second, hand-maintained list."""
    if connection.type_alias:
        return connection.type_alias
    normalized_name = _normalized(connection.destination_name)
    for label in _SETTLEMENT_SERVICE_LABELS_PT:
        if normalized_name.startswith(label):
            return label
    return None


def _destination_mention_span(
    segment_normalized: str, connection: _KnownConnection
) -> tuple[int, int] | None:
    if _normalized(connection.destination_name) != "local desconhecido":
        exact = re.search(
            rf"\b{re.escape(_normalized(connection.destination_name))}\b", segment_normalized
        )
        if exact:
            return exact.start(), exact.end()
    alias = _service_alias_for(connection)
    if alias:
        alias_match = re.search(rf"\b{re.escape(alias)}\b", segment_normalized)
        if alias_match:
            return alias_match.start(), alias_match.end()
    return None


# Phase 24J.5 — Issue 1 (False Containment/Same-Location Claim). Confirmed
# live: "Você pode encontrá-la na praça central, bem no coração da vila"
# for a service that is actually a SEPARATE connected Location, not the
# current one. Distinct from the direction/route check above — a
# containment claim can be false even with NO cardinal direction stated
# at all. Deliberately narrow, per the governing spec's own instruction:
# only the explicit containment shape ("fica NA praça", "fica DENTRO DA
# praça", "É AQUI na praça", "fica NESTE MESMO local") is a claim; "fica
# perto daqui" (near, not in) is loose natural wording and must never be
# rejected merely for mentioning the hub as a reference point.
#
# The containment preposition must be DIRECTLY followed by the hub word
# itself (only "mesmo" tolerated in between) — a first version instead
# checked "na"/"no" and a hub word ANYWHERE in the same clause, and a
# regression test caught it immediately: "Ela fica NA PARTE norte DA
# praça" is a legitimate relative-direction phrase (the existing
# direction check above already accepts it), but it also contains "fica",
# "na", and "praça" somewhere in the same sentence — none of them
# adjacent. Requiring direct adjacency is what actually distinguishes a
# containment claim ("na praça") from a directional reference that merely
# mentions the hub ("na parte norte DA praça" — "da", not "na", precedes
# "praça" itself).
_CONTAINMENT_CLAIM_PATTERN = re.compile(
    r"\b(?:fica|esta|e|encontra(?:-l[ao])?)\b\s*(?:aqui\s+)?"
    r"(?:n[ao]|dentro\s+d[ao])\s+(?:mesmo\s+)?"
    r"(?:praca(?:\s+central)?|centro\s+da\s+vila|coracao\s+da\s+vila|vila|local)\b"
    r"|\bneste\s+mesmo\s+local\b"
)


def _containment_violations_in_segment(
    segment_normalized: str,
    connections: list[_KnownConnection],
    carried_connection: _KnownConnection | None = None,
) -> list[str]:
    if not _CONTAINMENT_CLAIM_PATTERN.search(segment_normalized):
        return []
    destination_spans = [
        connection
        for connection in connections
        if _destination_mention_span(segment_normalized, connection) is not None
    ]
    if len(destination_spans) == 1:
        connection = destination_spans[0]
    elif not destination_spans and carried_connection is not None:
        # No destination named in THIS segment — a pronoun ("encontrá-LA")
        # referring back to the destination the previous segment named.
        # Same shape as _relational_geography_violations_in_segment's own
        # carry-forward, confirmed live for this exact check too.
        connection = carried_connection
    else:
        return []
    destination_label = (
        connection.destination_name
        if _normalized(connection.destination_name) != "local desconhecido"
        else (_service_alias_for(connection) or connection.destination_name)
    )
    return [
        f"a resposta afirma que '{destination_label}' está no/dentro do local atual, mas ele é "
        "um destino SEPARADO conectado a partir daqui (não o mesmo local); descreva-o apenas "
        "pela conexão real (direção/rota), nunca como parte do local atual"
    ]


def _relational_geography_violations_in_segment(
    segment_normalized: str,
    connections: list[_KnownConnection],
    carried_connection: _KnownConnection | None = None,
) -> tuple[list[str], _KnownConnection | None]:
    """Checks one sentence-level segment; returns (violations, updated
    carry). `carried_connection` is the destination the PREVIOUS segment
    was about — natural Portuguese routinely splits a reveal and its
    direction across two sentences with a pronoun ("A Estalagem... Ela
    fica a leste."), and a segment with a direction/route mention but no
    destination mention of its own falls back to it. Confirmed via live
    trace as a real gap: exactly that two-sentence shape let a wrong
    direction through with zero violations, because the sentence WITH the
    direction word had no destination name in it at all to correlate
    against.
    """
    mentions: list[tuple[int, str, str]] = []
    for direction in _DIRECTION_WORDS_PT:
        for m in re.finditer(rf"\b{direction}\b", segment_normalized):
            mentions.append((m.start(), "direction", direction))
    for route_kind in _ROUTE_KIND_WORDS_PT:
        for m in re.finditer(rf"\b{route_kind}\w*\b", segment_normalized):
            mentions.append((m.start(), "route_kind", route_kind))

    destination_spans = [
        (span[0], span[1], connection)
        for connection in connections
        for span in (_destination_mention_span(segment_normalized, connection),)
        if span is not None
    ]
    next_carry = (
        max(destination_spans, key=lambda span: span[1])[2] if destination_spans else carried_connection
    )

    if not mentions:
        return [], next_carry

    if not destination_spans:
        if carried_connection is None:
            return [], next_carry
        # No destination named in THIS segment at all — every mention is
        # about the carried-forward destination, not a proximity choice.
        violations = []
        for _pos, kind, word in mentions:
            connection = carried_connection
            claimed_matches = (
                word == connection.direction if kind == "direction" else word == connection.route_kind
            )
            if not claimed_matches:
                correct = connection.direction if kind == "direction" else connection.route_kind
                destination_label = (
                    connection.destination_name
                    if _normalized(connection.destination_name) != "local desconhecido"
                    else (_service_alias_for(connection) or connection.destination_name)
                )
                violations.append(
                    f"a direção ou rota descrita para '{destination_label}' entra em conflito "
                    f"com a geografia autoritativa (a conexão registrada usa '{correct}'); "
                    "reescreva usando apenas a conexão fornecida para esse destino"
                )
        return violations, next_carry

    violations = []
    for pos, kind, word in mentions:
        nearest_start, nearest_end, connection = min(
            destination_spans,
            key=lambda span: min(abs(pos - span[0]), abs(pos - span[1])),
        )
        claimed_matches = (
            word == connection.direction if kind == "direction" else word == connection.route_kind
        )
        if not claimed_matches:
            correct = connection.direction if kind == "direction" else connection.route_kind
            destination_label = (
                connection.destination_name
                if _normalized(connection.destination_name) != "local desconhecido"
                else (_service_alias_for(connection) or connection.destination_name)
            )
            violations.append(
                f"a direção ou rota descrita para '{destination_label}' entra em conflito "
                f"com a geografia autoritativa (a conexão registrada usa '{correct}'); reescreva "
                "usando apenas a conexão fornecida para esse destino"
            )
    return violations, next_carry


_REFERENTIAL_HINT_PATTERN = re.compile(r'se refere a "([^"]+)"')


def _referential_hint_connection(
    context: str, connections: list[_KnownConnection]
) -> _KnownConnection | None:
    """If _referential_continuity_hint fired for this turn (its own
    marker text is embedded verbatim in the CURRENT TURN BLOCK section of
    context), resolve its named referent to the matching known
    connection — an EXACTLY-ONE match only, the same safe-failure-mode
    every other resolver in this codebase uses.
    """
    match = _REFERENTIAL_HINT_PATTERN.search(context)
    if not match:
        return None
    referent = _normalized(match.group(1))
    candidates = [
        connection
        for connection in connections
        if _service_alias_for(connection) == referent
        or _normalized(connection.destination_name) == referent
    ]
    return candidates[0] if len(candidates) == 1 else None


def _find_canon_violations(text: str, context: str, player_input: str) -> list[str]:
    """Detect claims that expand persistent world canon without support.

    These are the ONLY violations allowed to trigger the epistemic-refusal
    fallback ("— Não sei dizer.") — they concern objective, persistent facts
    about the world (geography, history, factions, structures...), not prose
    style or ordinary social conversation.
    """
    normalized_text = _normalized(text)
    normalized_context = _normalized(_authoritative_context_only(context))
    normalized_input = _normalized(player_input)
    violations = []
    for concept, pattern in _PERSISTENT_CONCEPTS.items():
        if not re.search(pattern, normalized_text) or re.search(pattern, normalized_context):
            continue
        came_from_player = re.search(pattern, normalized_input) is not None
        if came_from_player:
            denial_pattern = (
                rf"(nao\s+(ha|existe|conheco|sei)|nunca\s+(ouvi|vi)|desconheco)"
                rf".{{0,60}}{pattern}|{pattern}.{{0,60}}"
                rf"(nao\s+(conheco|sei)|nunca\s+(ouvi|vi)|desconheco)"
            )
            if re.search(denial_pattern, normalized_text):
                continue
        origin = "suposição do jogador" if came_from_player else "invenção da resposta"
        violations.append(
            f"conceito persistente não autorizado ({origin}): {concept!r}; "
            "pode apenas negar ou admitir desconhecimento, sem validá-lo nem acrescentar detalhes"
        )

    quantified_history = (
        r"\b(um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|vinte|trinta|"
        r"quarenta|cinquenta|sessenta|\d+)\s+anos?\b"
    )
    if re.search(quantified_history, normalized_text) and not re.search(
        quantified_history, normalized_context
    ):
        violations.append("biografia ou duração histórica quantificada sem fato canônico")
    if re.search(r"\b(alguns dizem|contam que|ouvi dizer|dizem que)\b", normalized_text) and "[rumor" not in normalized_context:
        violations.append("rumor atribuído a terceiros sem conhecimento RUMOR fornecido")
    invented_history = (
        r"\b(como a maioria|nao me lembro de quando|antigamente|naquela epoca|outrora)\b"
        r"|\bquando\b.{0,50}\bera\b"
        r"|\bantes\b.{0,80}\b(era|havia|existia|ficava|acontecia|faziam|jogavam)\b"
        r"|\bja foi\b"
        r"|\bvi\b.{0,60}\b(primeir\w*|virar\w*|crescer\w*)\b"
    )
    if re.search(invented_history, normalized_text) and not re.search(
        invented_history, normalized_context
    ):
        violations.append("passado histórico ou memória coletiva não fornecidos pelo cânone")

    weekday_history = r"\b(segunda|terca|quarta|quinta|sexta|sabado|domingo)(-feira)?\b"
    if re.search(weekday_history, normalized_text) and not re.search(
        weekday_history, normalized_context
    ):
        violations.append("costume ou calendário social não fornecido pelo cânone")

    for route_kind in ("estrada", "trilha", "ponte"):
        for direction in ("norte", "sul", "leste", "oeste", "nordeste", "noroeste", "sudeste", "sudoeste"):
            response_has_pair = any(
                re.search(rf"\b{route_kind}\w*\b", segment)
                and re.search(rf"\b{direction}\b", segment)
                for segment in re.split(r"[.\n]", normalized_text)
            )
            context_has_pair = any(
                re.search(rf"\b{route_kind}\w*\b", segment)
                and re.search(rf"\b{direction}\b", segment)
                for segment in normalized_context.splitlines()
            )
            if response_has_pair and not context_has_pair:
                violations.append(
                    f"combinação geográfica não registrada: {route_kind} + direção {direction}"
                )

    # Phase 24J.4 — Issue 1, the destination-specific correlation the check
    # above cannot do (see _relational_geography_violations_in_segment's own
    # docstring): the loop above only asks whether a vocabulary combination
    # exists SOMEWHERE in context, which a real-but-unrelated connection can
    # satisfy. This asks whether THIS destination's OWN connection actually
    # has the direction/route claimed for it. Complementary, not a
    # replacement — kept as a separate check so a genuinely novel
    # combination with no destination mentioned nearby still gets caught
    # by the coarser check above.
    known_connections = _parse_known_connections(_authoritative_context_only(context))
    if known_connections:
        # Phase 24J.4 — a vague follow-up ("Onde ela fica?") answered with
        # NO destination word at all in the response ("Pode encontrá-la na
        # parte leste...") leaves every segment with nothing to correlate
        # against — confirmed via live trace. narrator._referential_
        # continuity_hint (24J.3) already names the likely referent for
        # exactly this shape of question, embedded in the CURRENT TURN
        # BLOCK section of context; seeding the carry-forward with it
        # means the SAME destination correlation applies even when the
        # response itself never names anything.
        carried_connection = _referential_hint_connection(context, known_connections)
        for segment in re.split(r"[.\n]", normalized_text):
            segment_violations, carried_connection = _relational_geography_violations_in_segment(
                segment, known_connections, carried_connection
            )
            violations.extend(segment_violations)
            # Phase 24J.5 — a separate relationship from direction/route:
            # does the response claim this destination IS the current
            # location, not merely a place reachable from it. See
            # _containment_violations_in_segment's own docstring.
            violations.extend(
                _containment_violations_in_segment(segment, known_connections, carried_connection)
            )

    if "nothing about what exists beyond it" in normalized_context:
        word_count = len(re.findall(r"\b\w+\b", normalized_text))
        if word_count > 12:
            violations.append(
                "a resposta a uma lacuna explícita sobre o que existe além deve ser somente desconhecimento"
            )
    unsupported_terms = re.findall(
        r"- '([^']+)' appears only in the player's assumption", normalized_context
    )
    if unsupported_terms:
        word_count = len(re.findall(r"\b\w+\b", normalized_text))
        if word_count > 15:
            violations.append(
                "a resposta elaborou uma suposição do jogador marcada como ausente do cânone"
            )
    return violations


_COMBAT_ACTION_VERBS = (
    r"ataca(?:m|ndo)?|atacou|atacaram|golpeia(?:m|ndo)?|golpeou|golpearam|"
    r"acerta(?:m|ndo)?|acertou|acertaram|erra(?:m|ndo)?|errou|erraram|"
    r"fere(?:m)?|feriu|feriram|fere?indo|"
    r"defende(?:m|ndo)?|defendeu|defenderam|"
    r"interv[ée]m|intervindo|intervieram|"
    r"luta(?:m|ndo)?|lutou|lutaram|"
    r"saca(?:m|ndo)?|sacou|sacaram|"
    r"empunha(?:m|ndo)?|empunhou|empunharam"
)


def _unauthorized_combatant_message(name: str) -> str:
    return (
        f"'{name}' age como combatente (ataca, defende ou intervém fisicamente na luta) "
        "sem constar em ACTIVE COMBAT PARTICIPANTS; NPCs apenas visíveis na cena são "
        "espectadores e nunca entram em combate por conta da narrativa"
    )


def _visible_npc_names(context: str) -> list[str]:
    match = re.search(r"(?:^|\n)VISIBLE NPCS\n((?:-.*\n?)*)", context)
    if not match:
        return []
    names = []
    for line in match.group(1).splitlines():
        entry = re.match(r"-\s*(.+?)\s*\(", line.strip())
        if entry:
            names.append(entry.group(1).strip())
    return names


def _combat_participant_names(context: str) -> set[str] | None:
    """Names authorized to fight this turn, or None when no combat is active."""
    match = re.search(r"(?:^|\n)ACTIVE COMBAT PARTICIPANTS\n((?:-.*\n?)*)", context)
    if not match:
        return None
    names = set()
    for line in match.group(1).splitlines():
        entry = re.match(r"-\s*(.+?)\s*\(", line.strip())
        if entry:
            names.add(entry.group(1).strip())
    return names


def _find_unauthorized_combatant_violations(text: str, context: str) -> list[str]:
    """Flag a bystander NPC (visible but not an ACTIVE COMBAT PARTICIPANT)
    written as taking a combat action — e.g. a local jumping in to help.

    Only checked while combat is actually active (participant list present);
    outside combat any NPC may act freely."""
    participants = _combat_participant_names(context)
    if participants is None:
        return []
    normalized_text = _normalized(text)
    for name in _visible_npc_names(context):
        if name in participants:
            continue
        first = re.escape(_normalized(name.split()[0]))
        if re.search(rf"\b{first}\b[^.\n]{{0,40}}?\b(?:{_COMBAT_ACTION_VERBS})\b", normalized_text):
            return [_unauthorized_combatant_message(name)]
    return []


def _drop_unauthorized_combatant_segments(text: str, context: str) -> str:
    """Granular fallback: remove only the paragraph(s) giving a bystander NPC
    combat agency, preserving the rest of the (otherwise valid) narration."""
    paragraphs = _split_paragraphs(text)
    kept_paragraphs = [
        paragraph
        for paragraph in paragraphs
        if not _find_unauthorized_combatant_violations(paragraph, context)
    ]
    return "\n\n".join(kept_paragraphs).strip()


# Verbs that legitimately bring a bystander NPC into an ongoing conversation —
# only after one of these narrates them arriving may they be voiced at all.
_NPC_ENTRANCE_VERBS = re.compile(
    r"\b(?:chega(?:m)?|chegou|chegaram|entra(?:m)?|entrou|entraram|"
    r"aparece(?:m)?|apareceu|apareceram|surge(?:m)?|surgiu|surgiram|"
    r"aproxima(?:m)?(?:-se)?|aproximou-se|aproximaram-se|"
    r"interrompe(?:m)?|interrompeu|interromperam|"
    r"junta(?:m)?-se|juntou-se|juntaram-se)\b",
    re.IGNORECASE,
)


def _unauthorized_speaker_message(name: str) -> str:
    if name == _UNRESOLVED_TURN_SENTINEL:
        return (
            "a resposta narra mais de uma fala/turno de diálogo sem interlocutor "
            "autorizado; escreva no máximo a primeira fala de quem se aproxima e "
            "pare — não invente uma troca inteira, nem uma resposta do protagonista, "
            "sem que o jogador tenha escrito outra ação"
        )
    return (
        f"'{name}' recebe fala atribuída sem ser o interlocutor ativo nem ter sido "
        "apresentado entrando na cena; numa conversa em andamento, um espectador visível "
        "pode no máximo um aparte curto — além disso, só depois de uma cena explícita de "
        "chegada/aproximação/interrupção"
    )


_QUOTE_MARK = re.compile(r'["“]')


_COLON_THEN_DASH_QUOTE = re.compile(r":\s*—")


def _paragraph_has_spoken_dialogue(paragraph: str) -> bool:
    """True for a quote-mark paragraph ("Nome disse, '...'") OR the
    dash-led screenplay style this codebase's own dialogue convention
    actually uses ("— fala — verbo") — _is_dialogue_paragraph already
    recognizes the dash-prefixed and colon-attributed shapes; this adds
    the inline-quote-mark shape _paragraph_speaker_among's stricter
    patterns miss, and a colon-then-dash mid-paragraph ("... e
    responde: — Meu nome é Lena.") — a real, fulfilled reply, not the
    dangling-promise shape _find_unfulfilled_speech_promise_violations
    exists to catch, which _is_dialogue_paragraph alone would miss
    since it only recognizes a dash that OPENS the paragraph."""
    return (
        _is_dialogue_paragraph(paragraph)
        or bool(_QUOTE_MARK.search(paragraph))
        or bool(_COLON_THEN_DASH_QUOTE.search(paragraph))
    )


_SPEECH_PROMISE_PARAGRAPH = re.compile(
    rf"\b(?:{_SPEECH_VERBS}|inclina(?:-se)?|estende|aponta|debru[çc]a(?:-se)?)\b[^.\n]*:",
    re.IGNORECASE,
)
_UNFULFILLED_SPEECH_PROMISE_MESSAGE = (
    "a resposta promete uma fala ('responde:', 'inclina-se... :', etc.) "
    "mas nunca a entrega em lugar nenhum do texto; ou complete a fala prometida "
    "imediatamente, ou reescreva sem prometer uma fala que não vai vir"
)


def _find_unfulfilled_speech_promise_violations(text: str) -> list[str]:
    """A distinct local-model failure mode from an outright empty response:
    the draft narrates right up to the edge of an NPC's line — "... e
    responde:", "Ela se inclina... com um ar confidencial:" — and then
    never actually delivers it anywhere in the draft. The colon-promise
    doesn't have to be the very end of its paragraph — the model just as
    often keeps narrating past it in the same paragraph (more scene-
    setting prose, never the promised line) as it does leaving it fully
    dangling at the end, sometimes across several such promises in a
    row, leaving the player's direct question (often one
    with no obvious canned answer, like the NPC's own name) completely
    unanswered while reading as if a reply were coming. Only fires when
    NO paragraph in the whole draft has any spoken dialogue at all — a
    real reply anywhere after the promise means it was fulfilled."""
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []
    if any(_paragraph_has_spoken_dialogue(paragraph) for paragraph in paragraphs):
        return []
    if any(_SPEECH_PROMISE_PARAGRAPH.search(paragraph.strip()) for paragraph in paragraphs):
        return [_UNFULFILLED_SPEECH_PROMISE_MESSAGE]
    return []


def _single_unattributed_quoted_speaker(paragraph: str, visible_npcs: list[str]) -> str | None:
    """Fallback for real dialogue this local model writes in a shape
    _paragraph_speaker_among's stricter patterns don't recognize — e.g.
    "Aldric Draven assente, ... 'Sim, temos...'", where the speech verb
    ("assente") isn't in _SPEECH_VERBS and isn't adjacent to the name.
    Deliberately narrow: only fires when the paragraph actually contains
    spoken dialogue AND exactly one visible NPC's name appears in it at
    all — an ambiguous multi-name paragraph is left to the stricter
    checks rather than guessed at, same caution as every other Phase 19
    validator."""
    if not _paragraph_has_spoken_dialogue(paragraph):
        return None
    mentioned = [
        name
        for name in visible_npcs
        if name and re.search(rf"\b{re.escape(name.split()[0])}\b", paragraph)
    ]
    return mentioned[0] if len(mentioned) == 1 else None


_UNRESOLVED_TURN_SENTINEL = "(diálogo adicional não atribuível)"


def _scan_unauthorized_speakers(
    paragraphs: list[str], visible_npcs: list[str], active_interlocutor_name: str
):
    """Yield (paragraph, unauthorized_speaker) for each paragraph, tracking NPC
    entrances as they're narrated so a later paragraph may legitimately voice
    an NPC who was just explicitly introduced joining the scene.

    When no interlocutor was ever mechanically authorized (the multi-NPC
    ambiguity case — see engine._handle_talk), a scene may still
    legitimately OPEN with one NPC's unattributed greeting/offer (nobody
    has been resolved as a target yet, but someone approaching and
    speaking first is normal). What is never legitimate is a SECOND
    quoted exchange nobody can be named for in the same draft — that is
    the model writing a whole back-and-forth (routinely including a
    fabricated protagonist reply attributed only by pronoun, "admitiu
    ele"/"disse ela", a shape none of the name-based checks recognize)
    with no player input driving the later turns. So exactly one
    unattributable quoted paragraph is tolerated per draft; any further
    one is flagged, regardless of whose voice it's meant to be.
    """
    authorized = {active_interlocutor_name} if active_interlocutor_name else set()
    # The budget rule below only ever applies with NO active interlocutor.
    # When one exists, an unresolved speaker on a dialogue paragraph is
    # assumed to be them continuing (unattributed follow-up paragraphs
    # from the same ongoing speaker are normal prose, not a new turn) —
    # exactly the pre-existing behavior, unchanged here.
    unattributed_quote_budget = 1
    # Someone standing right there may chime in once while a conversation
    # is going on (playtest: a bystander's natural aside was cut every
    # time). One line, from one bystander — never a second exchange.
    bystander_line_budget = 1 if active_interlocutor_name else 0
    for paragraph in paragraphs:
        if not _is_dialogue_paragraph(paragraph):
            normalized = _normalized(paragraph)
            for name in visible_npcs:
                if name in authorized:
                    continue
                first = re.escape(_normalized(name.split()[0]))
                if re.search(rf"\b{first}\b", normalized) and _NPC_ENTRANCE_VERBS.search(normalized):
                    authorized.add(name)
            speaker = _single_unattributed_quoted_speaker(paragraph, visible_npcs)
            if speaker is None and not active_interlocutor_name and _QUOTE_MARK.search(paragraph):
                if unattributed_quote_budget > 0:
                    unattributed_quote_budget -= 1
                else:
                    yield paragraph, _UNRESOLVED_TURN_SENTINEL
                    continue
            yield paragraph, (speaker if speaker and speaker not in authorized else None)
            continue
        speaker = _paragraph_speaker_among(paragraph, visible_npcs)
        if speaker is None:
            speaker = _single_unattributed_quoted_speaker(paragraph, visible_npcs)
        if speaker is None and not active_interlocutor_name:
            if unattributed_quote_budget > 0:
                unattributed_quote_budget -= 1
            else:
                yield paragraph, _UNRESOLVED_TURN_SENTINEL
                continue
        if speaker and speaker not in authorized and bystander_line_budget > 0:
            bystander_line_budget -= 1
            yield paragraph, None
            continue
        yield paragraph, (speaker if speaker and speaker not in authorized else None)


def _find_unauthorized_speaker_violations(
    text: str, context: str, active_interlocutor_name: str
) -> list[str]:
    """Only the active interlocutor may be given attributed dialogue. A
    different NPC merely visible in the scene is a bystander and may speak
    only once explicitly narrated joining the conversation."""
    visible_npcs = _visible_npc_names(context)
    if not visible_npcs:
        return []
    for _, unauthorized in _scan_unauthorized_speakers(
        _split_paragraphs(text), visible_npcs, active_interlocutor_name
    ):
        if unauthorized:
            return [_unauthorized_speaker_message(unauthorized)]
    return []


def _drop_unauthorized_speaker_segments(
    text: str, context: str, active_interlocutor_name: str
) -> str:
    """Granular fallback: remove only the paragraph(s) giving a bystander NPC
    unauthorized dialogue, preserving the rest of the narration."""
    visible_npcs = _visible_npc_names(context)
    kept_paragraphs = [
        paragraph
        for paragraph, unauthorized in _scan_unauthorized_speakers(
            _split_paragraphs(text), visible_npcs, active_interlocutor_name
        )
        if not unauthorized
    ]
    return "\n\n".join(kept_paragraphs).strip()


_AGENCY_VIOLATION_MESSAGE = (
    "a resposta usa o protagonista como personagem narrado; não escreva novas "
    "falas, gestos, ações ou reações para ele e mantenha mundo/NPCs como sujeitos"
)
_FABRICATED_TURN_MESSAGE = (
    "a resposta trata uma decisão, resposta ou desejo do protagonista como já "
    "manifestado, mas PLAYER INPUT não contém isso; não escreva o próximo turno do "
    "jogador nem a reação a ele, mesmo sem usar o nome do protagonista"
)

# Phase 24H — "Eu vou verificar." as bare (non-dialogue) narration: the
# narrator speaking in the protagonist's own first-person voice without
# ever using their name. "eu" is unambiguously a subject pronoun in
# Portuguese (unlike the name, which can legitimately appear as an
# object — "para Logan" — so subject_pattern below needs an exclusion
# this doesn't).
_FIRST_PERSON_NARRATION_PATTERN = re.compile(r"(?:^|[.\n]\s*)eu\s+\w+", re.IGNORECASE)

def _protagonist_agency_violations(
    text: str,
    character_name: str,
    mode: NarrationMode = "CONTINUATION",
    *,
    dialogue_context: bool | None = None,
    is_observation_turn: bool = False,
) -> list[str]:
    """Detect the narrator inventing NEW actions/dialogue for the protagonist.

    Mentioning the protagonist's name is fine when the protagonist is merely
    the OBJECT of an NPC/world action ("Osgar olhou para Logan"). It is only a
    violation when the protagonist is made the SUBJECT of a new action/reaction,
    is given a new line of dialogue via attribution ("— ... — diz Logan"), or an
    NPC/the world reacts to a decision of theirs that was never actually made
    ("Talven respeita o desejo de Logan de tomar uma decisão" — even though
    nothing in PLAYER INPUT ever stated that desire).

    OPENING is intentionally strict as well: the narrator may describe the world
    and canonical scene state, but it must not assign even a neutral position,
    awakening, materialization, posture or first action to the protagonist unless
    that state/action is explicitly present in authoritative context.

    dialogue_context overrides the first-person check's own dialogue-shape
    auto-detection (Phase 24H) for a `text` fragment that no longer carries
    its original paragraph's dialogue marker — the one caller that needs
    this is _drop_agency_violations, which checks one sentence at a time and
    would otherwise see a dash-led paragraph's LATER sentences (the dash
    isn't repeated per sentence) as bare narration. None of the other checks
    in this function need it: they all key on the character's literal name,
    which they already tolerate appearing inside dialogue text.
    """
    if not character_name:
        return []
    name = re.escape(character_name)

    for paragraph in _split_paragraphs(text):
        colon_speaker = _colon_dialogue_speaker(paragraph)
        if colon_speaker is not None and _mentions(colon_speaker, character_name):
            return [_AGENCY_VIOLATION_MESSAGE]

    speaks_pattern = re.compile(rf"\b(?:{_SPEECH_VERBS})\s+{name}\b", re.IGNORECASE)
    if speaks_pattern.search(text):
        return [_AGENCY_VIOLATION_MESSAGE]

    # Phase 24A.1 — the spec's own explicit forbidden examples ("Logan
    # thinks the man is lying", "Logan feels relieved", "Logan decides
    # to run", "Logan agrees") use an interpreted mental-state verb, not
    # a speech verb — speaks_pattern above never matches "pensa"/"sente"/
    # "acha"/"decide"/"concorda". "{name} pensa..." (name leading a
    # clause) is already caught by subject_pattern below regardless of
    # verb; this specifically covers the verb-first Portuguese word
    # order ("pensa Logan, satisfeito.") that subject_pattern's
    # name-must-lead-the-clause anchor cannot — confirmed missing by a
    # real regression test built from actual observed output. Deliberately
    # excludes "percebe"/"nota" (notices) — those are legitimately
    # sensory/perceptual in this codebase's own established SENSATION
    # != EMOTION policy (19E) and would false-positive on allowed
    # physical-perception narration.
    mental_state_pattern = re.compile(
        rf"\b(?:pensa|pensou|sente|sentiu|acha|achou|decide|decidiu|concorda|concordou)\s+{name}\b",
        re.IGNORECASE,
    )
    if mental_state_pattern.search(text):
        return [_AGENCY_VIOLATION_MESSAGE]

    # Phase 24H — every check above is anchored to the character's
    # literal name; none of them catch the narrator writing "Eu vou
    # verificar." as bare narration, which is the protagonist's voice
    # with the name simply omitted (spec's own required regression
    # case). Scoped to non-dialogue paragraphs only — an NPC's own
    # first-person speech ("— Eu vou até lá primeiro.") is legitimate
    # and must not be flagged; paragraph is the same granularity
    # _scan_unauthorized_speakers already uses for this distinction.
    for paragraph in _split_paragraphs(text):
        is_dialogue = (
            _paragraph_has_spoken_dialogue(paragraph)
            if dialogue_context is None
            else dialogue_context
        )
        if is_dialogue:
            continue
        if _FIRST_PERSON_NARRATION_PATTERN.search(paragraph):
            return [_AGENCY_VIOLATION_MESSAGE]

    # A fabricated protagonist reply doesn't always carry an explicit
    # "— ... — diz Logan" attribution the checks above look for — this
    # local model commonly writes it as a plain unattributed dialogue
    # line that self-identifies in first person instead ("— Eu... Sou
    # Logan, se alguém..."), especially answering an NPC's own direct
    # question. That self-identification alone is unambiguous regardless
    # of whether any NPC name is known yet (a first-contact scene has
    # none), so this check runs unconditionally, unlike the npc_name-
    # gated fabricated-turn checks below.
    self_identifies_pattern = re.compile(
        rf"\b(?:sou|eu\s+sou|meu\s+nome\s+[ée])\s+(?:o\s+|a\s+)?{name}\b",
        re.IGNORECASE,
    )
    if self_identifies_pattern.search(text):
        return [_AGENCY_VIOLATION_MESSAGE]

    reacts_pattern = re.compile(
        rf"\b(?:{_REACTS_TO_DECISION_VERBS})\b[^.\n]{{0,60}}\b(?:{_DECISION_NOUNS})\s+de\s+{name}\b",
        re.IGNORECASE,
    )
    if reacts_pattern.search(text):
        return [_FABRICATED_TURN_MESSAGE]

    # Tolerate a short comma-bounded appositive between the name and the verb
    # ("Filipe, ofegante, tenta...") — otherwise it breaks the match entirely
    # and lets a fabricated action/dialogue slip through right after it.
    subject_pattern = re.compile(
        rf"(?:^|[.\n—]\s*){name}\b(?:\s*,[^.\n]{{0,60}}?,)?\s+(?:se\s+)?(\w+)",
        re.IGNORECASE,
    )

    for match in subject_pattern.finditer(text):
        preceding = text[max(0, match.start() - 20): match.start()]

        if re.search(rf"\b{_OBJECT_PREPOSITIONS}\s*$", preceding, re.IGNORECASE):
            continue

        verb = _normalized(match.group(1))

        # During OPENING the protagonist may be the grammatical subject only
        # for the involuntary physical result of the transportation.
        if mode == "OPENING" and verb in _OPENING_ALLOWED_SUBJECT_VERBS:
            continue

        # Sensory/perceptual verbs are legitimate in any mode — see
        # _SENSORY_PERCEPTION_VERBS' own docstring (24J.2).
        if verb in _SENSORY_PERCEPTION_VERBS:
            continue

        # Movement-completion verbs are legitimate in any mode — see
        # _MOVEMENT_RESULT_VERBS' own docstring (24J.3).
        if verb in _MOVEMENT_RESULT_VERBS:
            continue

        # "Logan abre/empurra a porta e entra." is the same authoritative-
        # transit case as _MOVEMENT_RESULT_VERBS above, but these verbs
        # alone cannot join that set — an unqualified "abre"/"empurra" is
        # exactly how a genuinely invented action would read too ("Logan
        # abre a bolsa e rouba...", "Logan empurra o guarda e foge").
        # Narrowly scoped to the doorway/passage object right after the
        # verb. "abre" confirmed via live trace (req=nr_4023e6ee9705:
        # "Logan abre a porta da estalagem e entra."); "empurra" confirmed
        # via a later live re-validation run (req=nr_e3c53e7eaa21: "Logan
        # empurra a porta pesada da estalagem e entra.") — both fell to
        # the generic PLAYER_AGENCY fallback even though the mechanical
        # fact was an authoritative, already-resolved arrival.
        if verb in {"abre", "empurra"} and re.search(
            r"\bporta[s]?\b", _normalized(text[match.end(): match.end() + 25])
        ):
            continue

        # Observation-framing verbs are legitimate ONLY when this turn's
        # own authoritative mechanical fact confirms the backend actually
        # resolved an observation action — see _OBSERVATION_FRAMING_VERBS'
        # own docstring (24J.5).
        if is_observation_turn and verb in _OBSERVATION_FRAMING_VERBS:
            continue

        return [_AGENCY_VIOLATION_MESSAGE]
    return []


def _extract_character_name(context: str) -> str:
    match = re.search(r"(?:^|\n)CURRENT PLAYER\nName: ([^\n(]+)", context)
    return match.group(1).strip() if match else ""


def _extract_active_npc_name(context: str) -> str:
    match = re.search(r"(?:^|\n)ACTIVE NPC CONTEXT\nName: ([^\n(]+)", context)
    return match.group(1).strip() if match else ""


def _extract_active_transported_person_name(
    context: str,
) -> str:
    match = re.search(
        r"(?:^|\n)ACTIVE TRANSPORTED PERSON CONTEXT\n"
        r"Name: ([^\n(]+)",
        context,
    )

    return (
        match.group(1).strip()
        if match
        else ""
    )


def _extract_active_interlocutor_name(
    context: str,
) -> str:
    return (
        _extract_active_npc_name(context)
        or _extract_active_transported_person_name(
            context
        )
    )


def _private_location_fields(context: str) -> dict[str, str]:
    section_match = re.search(
        r"CANONICAL LOCATION CONTEXT[^\n]*\n(.*?)(?:\n\n|\Z)",
        context,
        re.DOTALL,
    )
    if not section_match:
        return {}
    fields = {}
    for label in ("Name", "Region"):
        match = re.search(rf"^{label}:\s*([^\n]+)", section_match.group(1), re.MULTILINE)
        if not match:
            continue
        # Phase 24J.1 added a trailing "(HIDDEN — ...)"/"(DIRECTLY
        # PERCEPTIBLE — ...)" annotation on these lines (context_builder's
        # location_lines) — strip it so downstream consumers (the hidden-
        # name guard, relevance grounding, targeted repair) keep getting
        # the bare proper noun, not the annotation text along with it.
        value = re.sub(r"\s*\([^()]*\)\s*$", "", match.group(1).strip()).strip()
        if value and value.lower() != "unknown":
            fields[label] = value
    return fields


def _direct_question_grounding_section(context: str) -> str:
    match = re.search(
        r"(?:^|\n)DIRECT QUESTION GROUNDING\n(.*?)(?:\n\n|\Z)", context, re.DOTALL
    )
    return match.group(1) if match else ""


def _direct_question_grounding_fact(context: str) -> str | None:
    """The specific fact context_builder's DIRECT QUESTION GROUNDING
    section (Phase 24J.1 Step 4) authorized for the current question, if
    any — used by the repair pipeline (Step 6) to answer a NOT_ADDRESSED
    question with a real, backend-supplied fact instead of silence."""
    section = _direct_question_grounding_section(context)
    match = re.search(r"^Authorized answer:\s*([^\n]+)", section, re.MULTILINE)
    return match.group(1).strip() if match else None


def _direct_question_grounding_is_explicit_ignorance(context: str) -> bool:
    """True when the grounding section exists but explicitly states no
    confirmed answer is available — the repair pipeline should produce a
    genuine in-character admission of not knowing rather than silence."""
    return "No confirmed answer available" in _direct_question_grounding_section(context)


_UNITS_PT = (
    "zero", "um", "dois", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove",
    "dez", "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete",
    "dezoito", "dezenove",
)
_TENS_PT = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa")
_HUNDREDS_PT = (
    "", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
    "seiscentos", "setecentos", "oitocentos", "novecentos",
)


def _spell_pt(number: int) -> str:
    """Brazilian Portuguese cardinal (masculine, unaccented), 0..999999."""
    if number < 20:
        return _UNITS_PT[number]
    if number < 100:
        tens, units = divmod(number, 10)
        return _TENS_PT[tens] + (f" e {_UNITS_PT[units]}" if units else "")
    if number < 1000:
        if number == 100:
            return "cem"
        hundreds, rest = divmod(number, 100)
        return _HUNDREDS_PT[hundreds] + (f" e {_spell_pt(rest)}" if rest else "")
    thousands, rest = divmod(number, 1000)
    head = "mil" if thousands == 1 else f"{_spell_pt(thousands)} mil"
    if not rest:
        return head
    joiner = " e " if rest < 100 or rest % 100 == 0 else " "
    return head + joiner + _spell_pt(rest)


def _mentions_bronze_amount(text: str, amount: int) -> bool:
    """True when the text states this bronze amount the way a person would:
    "15 bronze", "quinze bronzes", "duas moedas de bronze", "15 de bronze".

    Confirmed live: Nemotron answered "— Quinze bronze." on every attempt and
    a digits-only check rejected it until a robotic fallback replaced the
    whole (correct) answer.
    """
    masculine = _spell_pt(amount)
    feminine = re.sub(r"\bum\b", "uma", masculine)
    feminine = re.sub(r"\bdois\b", "duas", feminine)
    feminine = re.sub(r"entos\b", "entas", feminine)
    spellings = {str(amount), f"{amount:,}".replace(",", "."), masculine, feminine}
    alternatives = "|".join(re.escape(spelling) for spelling in sorted(spellings, key=len, reverse=True))
    return re.search(
        # "e " before it means it's the tail of a larger number ("cento e quinze").
        rf"(?<![\w.])(?<!\be )(?<!\bmil )(?:{alternatives})(?:\s+(?:moedas?|pecas?|de|em))*\s+bronzes?\b",
        _normalized(text),
    ) is not None


def _find_missing_authorized_price_answer_violations(
    text: str, context: str, player_input: str
) -> list[str]:
    """A grounded direct price question must actually receive its price.

    The LLM remains responsible for natural wording, but it may not silently
    omit a backend-authorized current offer. This is deliberately narrower
    than a general relevance validator: it only applies when S1.3 supplied a
    numeric CURRENT OFFER for the speaker at hand.
    """
    if not is_price_question(player_input):
        return []
    section = _direct_question_grounding_section(context)
    match = re.search(r"^CURRENT OFFER:\s*(\d+)\s+bronze\.?$", section, re.MULTILINE | re.IGNORECASE)
    if match is None:
        return []
    amount = match.group(1)
    if _mentions_bronze_amount(text, int(amount)):
        return []
    return [
        "a pergunta direta de preço não foi respondida: informe explicitamente "
        f"o CURRENT OFFER autorizado de {amount} bronze"
    ]


def enforce_authorized_price_answer(
    text: str,
    context: str,
    player_input: str,
    active_interlocutor_name: str = "",
) -> str:
    """Final deterministic guard after every narrative validation layer."""
    if not _find_missing_authorized_price_answer_violations(text, context, player_input):
        return text
    grounded_fact = _direct_question_grounding_fact(context)
    if grounded_fact and active_interlocutor_name:
        logger.warning(
            "final narrative guard restored omitted authorized economic answer speaker=%s",
            active_interlocutor_name,
        )
        return f"— {grounded_fact} — responde {active_interlocutor_name}."
    return text


def _npc_knowledge(context: str) -> str:
    match = re.search(
        r"(?:^|\n)NPC KNOWLEDGE\n(.*?)(?:\n\nPLAYER KNOWLEDGE|\Z)",
        context,
        re.DOTALL,
    )
    return match.group(1) if match else ""


def _active_npc_location(context: str) -> str:
    section_match = re.search(
        r"(?:^|\n)ACTIVE NPC CONTEXT\n(.*?)(?:\n\n|\Z)", context, re.DOTALL
    )
    if not section_match:
        return ""
    match = re.search(r"^Location:\s*([^\n]+)", section_match.group(1), re.MULTILINE)
    return match.group(1).strip() if match else ""


def _find_hidden_name_violations(
    text: str, context: str, active_interlocutor_name: str
) -> list[str]:
    """Private canonical metadata is not automatically narrator-visible truth.

    Without an active interlocutor capable of communicating it, a location or
    region whose knowledge flag is NO must not appear in the prose merely
    because its private database name was included in the context.
    """
    private_fields = _private_location_fields(context)
    npc_knowledge = _npc_knowledge(context)
    # A resident NPC (their own registered Location matches the current
    # location's canonical name) trivially knows where they live, the same
    # way any real innkeeper knows their own village's name without it
    # being a curated secret — this is ambient local knowledge, not a
    # KnowledgeFact that needs explicit seeding (Phase 24J.1, confirmed via
    # live trace: an innkeeper with no seeded NPCKnowledge row was blocked
    # from ever answering "what village is this?").
    location_name = private_fields.get("Name", "")
    npc_is_local = bool(
        active_interlocutor_name
        and location_name
        and _mentions_canonical_name(_active_npc_location(context), location_name)
    )
    unknown_names = []
    for kind, field in (("location", "Name"), ("region", "Region")):
        flag = re.search(
            rf"Current {kind} canonical name known to player:\s*NO",
            context,
            re.IGNORECASE,
        )
        name = private_fields.get(field)
        if not flag or not name or not _mentions_canonical_name(text, name):
            continue
        npc_can_reveal = npc_is_local or (
            active_interlocutor_name and _mentions_canonical_name(npc_knowledge, name)
        )
        if not npc_can_reveal:
            unknown_names.append(name)
    if unknown_names:
        return [_HIDDEN_NAME_MESSAGE]
    return []


def _drop_hidden_name_segments(
    text: str, context: str, active_interlocutor_name: str
) -> str:
    """Granular fallback: remove only the paragraph(s) that leak a canonical
    name the player doesn't know, preserving the rest of the narration."""
    paragraphs = _split_paragraphs(text)
    kept_paragraphs = [
        paragraph
        for paragraph in paragraphs
        if not _find_hidden_name_violations(paragraph, context, active_interlocutor_name)
    ]
    return "\n\n".join(kept_paragraphs).strip()


def _find_unsolicited_opening_interaction_violations(
    text: str,
    mode: NarrationMode,
    active_interlocutor_name: str,
    simulated_player_names: list[str],
) -> list[str]:
    if mode != "OPENING" or active_interlocutor_name:
        return []
    paragraphs = _split_paragraphs(text)
    native_dialogue = any(
        _is_dialogue_paragraph(paragraph)
        and not _paragraph_speaks_for_simulated_player(
            paragraphs, index, simulated_player_names
        )
        for index, paragraph in enumerate(paragraphs)
    )
    native_approach = any(
        re.search(
            r"\b(?:se\s+aproxima|aproxima-se|vem\s+ate|dirige-se\s+a)\b",
            _normalized(paragraph),
        )
        and not any(_mentions(paragraph, name) for name in simulated_player_names)
        for paragraph in paragraphs
    )
    if native_dialogue or native_approach:
        return [_UNSOLICITED_OPENING_INTERACTION_MESSAGE]
    return []


def _find_style_violations(text: str) -> list[str]:
    """Detect cosmetic prose/format issues for diagnostics only.

    Style problems are deliberately NON-BLOCKING: they never trigger LLM
    regeneration, dropping content, or epistemic fallback. A slightly clumsy
    sentence is preferable to throwing away an otherwise valid grounded turn.
    """
    lowered = text.lower()
    violations = [
        f"expressão decorativa proibida: {marker!r}"
        for marker in _FORBIDDEN_STYLE_MARKERS
        if marker in lowered
    ]
    if '"' in text:
        violations.append("fala direta usa aspas em vez de travessão")

    paragraphs = [
        paragraph
        for paragraph in re.split(r"\n\s*\n", text.strip())
        if paragraph.strip()
    ]
    if len(paragraphs) > 3:
        violations.append("resposta desproporcional: use no máximo três parágrafos curtos")
    return violations


# Phase 24K — Repetition & Narrative Style Quality. NON-BLOCKING (same
# rule as every other style check above): flags robotic repetition for
# the trace/log only, never triggers regeneration or drops content —
# "do not ban reasonable recurring vocabulary" (spec) means a false
# positive here must never cost real, valid prose. Curated stock
# phrases + a lightweight lead-in comparison against the recent-history
# block already passed to narrate(), per the spec's own "prefer
# lightweight recent-history comparisons first" and "do NOT add
# embedding calls ... unless demonstrated necessary" — no second LLM
# call, no vector search.
_STOCK_PHRASES = (
    "sorri e responde",
    "faz uma pausa",
    "hesita por um momento",
    "olhos se estreitam",
    "olhos brilham",
    "inclina a cabeça",
    "cruza os braços",
    "solta um suspiro",
    "balança a cabeça",
    "franze a testa",
)

_RECENT_NARRATOR_RESPONSE = re.compile(
    r'Resposta (?:de [^:\n]+ anteriormente|narrada anteriormente): "(.*)"'
)

_LEAD_IN_WORDS = 5


def _lead_in(text: str) -> str:
    first_sentence = _split_sentences(text)[0] if _split_sentences(text) else text
    words = re.findall(r"\w+", _normalized(first_sentence))
    return " ".join(words[:_LEAD_IN_WORDS])


def _recent_narrator_responses(recent_history: str) -> list[str]:
    return _RECENT_NARRATOR_RESPONSE.findall(recent_history)


def _find_repetition_violations(text: str, recent_history: str) -> list[str]:
    past_responses = _recent_narrator_responses(recent_history)
    if not past_responses:
        return []

    violations = []
    normalized_text = _normalized(text)

    current_lead_in = _lead_in(text)
    if current_lead_in and any(
        current_lead_in == _lead_in(past) for past in past_responses
    ):
        violations.append(
            "início repetido: as mesmas primeiras palavras de um turno narrado recentemente; "
            "varie a abertura da resposta"
        )

    for phrase in _STOCK_PHRASES:
        if phrase in normalized_text and any(
            phrase in _normalized(past) for past in past_responses
        ):
            violations.append(
                f"frase feita repetida de um turno recente: {phrase!r}; descreva a mesma "
                "ação/reação com outras palavras"
            )

    return violations


# Phase 24J.1 Step 8 — near-verbatim reuse becomes a BLOCKING violation
# (triggers narrate()'s own revision loop), but ONLY when the current
# player turn is a direct question. Phase 24K's repetition check above
# stays non-blocking for everything else, per its own explicit "do not
# ban reasonable recurring vocabulary" rule — this is deliberately much
# narrower: a real playtest failure was the SAME generic non-answer
# ("Como posso ajudar você hoje?") appearing again on the very next
# turn, after a direct question. That specific pattern (a question,
# answered twice with the same stock line) is strong, reliable evidence
# of failure, not a stylistic tic worth merely logging.
_STALE_REPEAT_SIMILARITY_THRESHOLD = 0.85


# Phase 14 playtest: after "Faço meu turno de novo" and "Compro o martelo"
# Nemotron returned, word for word, its narration from TWO turns earlier —
# the second time narrating a refusal ("Não tem, não leva") for a purchase
# the backend had just completed. A near-verbatim copy of any recent turn is
# a failure whatever the player did, not only after a direct question.
_STALE_REPEAT_LOOKBACK = 3


def _find_stale_repeated_response_violations(text: str, recent_history: str, player_input: str) -> list[str]:
    past_responses = [
        response for response in _recent_narrator_responses(recent_history)[-_STALE_REPEAT_LOOKBACK:]
        if response.strip()
    ]
    normalized_text = _normalized(text)
    if not any(
        difflib.SequenceMatcher(None, normalized_text, _normalized(past)).ratio()
        >= _STALE_REPEAT_SIMILARITY_THRESHOLD
        for past in past_responses
    ):
        return []
    if classify_conversational_act(player_input) in _MUST_ADDRESS_ACTS:
        return [
            "a resposta repete quase literalmente um turno narrado recente sem "
            "justificativa — o jogador fez uma pergunta direta e recebeu, de novo, essencialmente "
            "a mesma fala; isso não é uma escolha intencional do interlocutor, é falha em "
            "reconhecer que uma NOVA pergunta foi feita"
        ]
    return [
        "a resposta copia quase literalmente um turno narrado recente; narre o que aconteceu "
        "AGORA, segundo AUTHORITATIVE MECHANICAL FACTS, com palavras novas"
    ]


def _split_paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text.strip()) if paragraph.strip()]


def _split_sentences(paragraph: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", paragraph) if sentence.strip()]


# A local model sometimes writes dialogue in screenplay style ('Nome: "..."')
# instead of the expected em-dash convention. Both must be recognized as
# dialogue, or every dialogue-aware check below silently misses this format.
_COLON_DIALOGUE_ATTRIBUTION = re.compile(
    r"^([A-ZÀ-Ý][\wÀ-ÿ'’]{1,40}(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’]{1,40}){0,2})\s*:\s*(?=[\"“—-])"
)


def _colon_dialogue_speaker(paragraph: str) -> str | None:
    match = _COLON_DIALOGUE_ATTRIBUTION.match(paragraph.strip())
    return match.group(1).strip() if match else None


def _is_dialogue_paragraph(paragraph: str) -> bool:
    stripped = paragraph.strip()
    return stripped.startswith(("—", "-")) or _colon_dialogue_speaker(paragraph) is not None


def _extract_simulated_player_names(
    context: str,
) -> list[str]:
    """
    Return the names of transported people relevant to the scene.

    The active transported interlocutor is included even if the visible
    list is absent or truncated.
    """

    names = []

    active_name = (
        _extract_active_transported_person_name(
            context
        )
    )

    if active_name:
        names.append(active_name)

    match = re.search(
        r"(?:^|\n)"
        r"(?:VISIBLE TRANSPORTED PEOPLE|VISIBLE PLAYERS)"
        r"\n((?:-.*\n?)*)",
        context,
    )

    if not match:
        return names

    for line in match.group(1).splitlines():
        entry = re.match(
            r"-\s*(.+?)\s*\(",
            line.strip(),
        )

        if not entry:
            continue

        name = entry.group(1).strip()

        if name not in names:
            names.append(name)

    return names


def _paragraph_speaks_for_simulated_player(
    paragraphs: list[str], index: int, simulated_player_names: list[str]
) -> bool:
    """Whether the dialogue paragraph at `index` belongs to a transported person. —
    either because it names one directly, or because the narration beat right
    before it (if any) just introduced one as the speaker."""
    if not simulated_player_names:
        return False
    if any(_mentions(paragraphs[index], name) for name in simulated_player_names):
        return True
    if index > 0 and not _is_dialogue_paragraph(paragraphs[index - 1]):
        if any(_mentions(paragraphs[index - 1], name) for name in simulated_player_names):
            return True
    return False


def _npc_meta_awareness_violation(
    paragraphs: list[str], index: int, simulated_player_names: list[str]
) -> bool:
    """True if a DIALOGUE paragraph reveals awareness of being inside a game —
    checked at paragraph, not sentence, granularity, since only the FIRST
    sentence of a spoken turn carries the leading dash; later sentences in the
    same turn are still that speaker talking. Exempt if the line belongs to a
    simulated player, who is allowed to know this."""
    paragraph = paragraphs[index]
    if not _is_dialogue_paragraph(paragraph):
        return False
    if _META_GAME_TERMS.search(paragraph) is None:
        return False
    return not _paragraph_speaks_for_simulated_player(paragraphs, index, simulated_player_names)


def _find_meta_awareness_violations(text: str, simulated_player_names: list[str]) -> list[str]:
    paragraphs = _split_paragraphs(text)
    if any(
        _npc_meta_awareness_violation(paragraphs, index, simulated_player_names)
        for index in range(len(paragraphs))
    ):
        return [
            "um habitante nativo usou conhecimento tecnológico ou de videogame incompatível "
            "com seu contexto; habitantes nativos não sabem que Everreach é um jogo porque "
            "Everreach não é um jogo. Pessoas transportadas podem conhecer esse vocabulário "
            "por sua vida anterior, mas isso não torna o mundo uma simulação"
        ]
    return []


def _drop_unsupported_segments(
    text: str, context: str, player_input: str, simulated_player_names: list[str] | None = None
) -> str:
    """Last-resort granular fallback: keep only the content that doesn't carry
    an unsupported canon claim or NPC meta-game awareness, instead of
    discarding the whole response. Meta-awareness drops the whole spoken turn
    (paragraph); canon claims are filtered sentence by sentence within it."""
    simulated_player_names = simulated_player_names or []
    paragraphs = _split_paragraphs(text)
    kept_paragraphs = []
    for index, paragraph in enumerate(paragraphs):
        if _npc_meta_awareness_violation(paragraphs, index, simulated_player_names):
            continue
        kept_sentences = [
            sentence
            for sentence in _split_sentences(paragraph)
            if not _find_canon_violations(sentence, context, player_input)
        ]
        if kept_sentences:
            kept_paragraphs.append(" ".join(kept_sentences))
    return "\n\n".join(kept_paragraphs).strip()


def _mentions(paragraph: str, name: str) -> bool:
    if not name:
        return False
    first_name = name.split()[0]
    return re.search(rf"\b{re.escape(first_name)}\b", paragraph, re.IGNORECASE) is not None


def _mentions_canonical_name(paragraph: str, name: str) -> bool:
    """Like `_mentions`, but for CANONICAL LOCATION/REGION names specifically.

    `_mentions`'s first-word-only shortcut is safe for people (a first name
    is rarely an ordinary word), but many location/region names lead with
    an everyday noun ("Campos de Kessler", "Vila de Sarn") — matching only
    that leading word caused real false-positive hidden-name violations
    against text that used the ordinary word ("campos" = fields/countryside)
    with no relation to the private proper name, discarding an already-safe,
    self-corrected response (Phase 24J.1, confirmed via live trace). Matches
    the full name as a phrase, or its last (typically most distinctive)
    word, but never a lone leading word shared with multi-word names.
    """
    if not name:
        return False
    words = name.split()
    if len(words) == 1:
        return _mentions(paragraph, name)
    full_pattern = r"\s+".join(re.escape(word) for word in words)
    if re.search(full_pattern, paragraph, re.IGNORECASE):
        return True
    last_word = words[-1]
    return re.search(rf"\b{re.escape(last_word)}\b", paragraph, re.IGNORECASE) is not None


def _paragraph_speaker_among(paragraph: str, candidates: list[str]) -> str | None:
    """Which of these candidate names (if any) does this paragraph explicitly
    establish as speaking — via 'Nome: "..."' screenplay attribution, or a
    speech-verb adjacent to a name ("— ... — diz Osgar", "Osgar pergunta: — ...")?

    Deliberately stricter than a bare name search: a name appearing inside the
    dialogue text itself is often vocative address ("E você, senhor Osgar?"),
    not proof of who is speaking — treating it as attribution would let a
    fabricated player line that merely addresses someone by name slip through.
    """
    colon_speaker = _colon_dialogue_speaker(paragraph)
    if colon_speaker is not None:
        for name in candidates:
            if name and _mentions(colon_speaker, name):
                return name
        return None
    for name in candidates:
        if not name:
            continue
        first = re.escape(name.split()[0])
        if re.search(rf"\b(?:{_SPEECH_VERBS})\s+{first}\b", paragraph, re.IGNORECASE):
            return name
        if re.search(rf"\b{first}\b\s*(?:,)?\s*(?:{_SPEECH_VERBS})\b", paragraph, re.IGNORECASE):
            return name
    return None


def _paragraph_attributed_speaker(paragraph: str, character_name: str, npc_name: str) -> str | None:
    speaker = _paragraph_speaker_among(paragraph, [npc_name, character_name])
    if speaker is None:
        return None
    return "npc" if speaker == npc_name else "player"


def _paragraph_establishes_speaker(paragraph: str, character_name: str, npc_name: str) -> str | None:
    """Who does this paragraph clearly establish as talking or about to talk —
    explicit attribution for a dialogue line, or simply being named as the
    actor in a narration beat (narration reliably names its own subject)."""
    if _is_dialogue_paragraph(paragraph):
        return _paragraph_attributed_speaker(paragraph, character_name, npc_name)
    if _mentions(paragraph, npc_name):
        return "npc"
    if _mentions_as_subject(paragraph, character_name):
        return "player"
    return None


_OBJECT_PREPOSITIONS = r"(?:de|da|do|para|pra|a|ao|com|sobre|por|em|contra|ate)"


def _mentions_as_subject(paragraph: str, name: str) -> bool:
    """Named other than as an object. Playtest: "O ancião ergue o queixo na
    direção de Logan antes de responder." made Logan the one about to speak,
    so the elder's own answer was cut as a fabricated player turn."""
    if not name:
        return False
    first = re.escape(_normalized(name.split()[0]))
    normalized = _normalized(paragraph)
    return any(
        not re.search(rf"\b{_OBJECT_PREPOSITIONS}\s+$", normalized[: match.start()])
        for match in re.finditer(rf"\b{first}\b", normalized)
    )


def _find_fabricated_turn_start(
    paragraphs: list[str], character_name: str, npc_name: str
) -> int | None:
    """Find where the narrator wrote the player's turn without ever naming them.

    The tell is the SHAPE: a dash-led line with no explicit speaker attribution
    (not the NPC's own continuing line, not the player's named line either).
    Two situations confirm it's the fabricated reply rather than the NPC's own
    uninterrupted monologue:
    - the narration beat right before it already frames the PLAYER as about to
      act/respond ("Logan sente-se... e responde") — that beat is itself the
      violation, and this dialogue line is its fabricated content; or
    - the NEXT paragraph explicitly re-establishes the NPC as speaking again —
      i.e. the NPC answering a line nobody in the scene actually said.
    A same-speaker monologue split across paragraphs has neither shape: the
    narration before it (if any) names the NPC, not the player, and nothing
    immediately after it re-introduces a speaker.
    """
    if not npc_name:
        return None
    for index, paragraph in enumerate(paragraphs):
        if not _is_dialogue_paragraph(paragraph):
            continue
        if _paragraph_attributed_speaker(paragraph, character_name, npc_name) is not None:
            continue  # explicitly attributed within the line itself

        prev_speaker = None
        if index > 0 and not _is_dialogue_paragraph(paragraphs[index - 1]):
            prev_speaker = _paragraph_establishes_speaker(paragraphs[index - 1], character_name, npc_name)

        # A line that addresses the active NPC and speaks in the first person
        # cannot be that NPC's own continuation. Local models commonly insert
        # exactly this shape after a LOOK action: "— Obrigado, senhor. O que me
        # aconselha?", then continue by making the NPC answer it. ("seu" is
        # left out: far more often a possessive, "o seu caminho", than a
        # form of address.)
        normalized_paragraph = _normalized(paragraph)
        addresses_npc = re.search(
            r"\b(?:senhor|senhora|dona)\b",
            normalized_paragraph,
        ) or (
            npc_name
            and re.search(
                rf"(?:^|[,;])\s*{re.escape(_normalized(npc_name.split()[0]))}\b",
                normalized_paragraph,
            )
        )
        first_person = re.search(
            r"\b(?:eu|me|meu|minha|vou|posso|preciso|agradeco|aconselha)\b",
            normalized_paragraph,
        )
        if addresses_npc and first_person:
            return index

        if prev_speaker == "npc":
            continue  # legitimately attributed by the narration beat right before it
        if prev_speaker == "player":
            return index  # the narration already fabricated the player's turn

        if index + 1 < len(paragraphs):
            if _paragraph_establishes_speaker(paragraphs[index + 1], character_name, npc_name) == "npc":
                return index
    return None


def _fabricated_turn_violations(text: str, character_name: str, npc_name: str) -> list[str]:
    if not character_name:
        return []
    if _find_fabricated_turn_start(_split_paragraphs(text), character_name, npc_name) is not None:
        return [_FABRICATED_TURN_MESSAGE]
    return []


def _drop_agency_violations(
    text: str,
    character_name: str,
    npc_name: str = "",
    mode: NarrationMode = "CONTINUATION",
    *,
    is_observation_turn: bool = False,
) -> str:
    """Remove fabricated protagonist dialogue/actions instead of accepting them.

    First truncates at the first fabricated player turn (see
    `_find_fabricated_turn_start`), then — within what's left — drops any
    sentence that still gives the protagonist a new line or reaction and
    everything after it in the same paragraph.
    """
    if not character_name:
        return text

    paragraphs = _split_paragraphs(text)
    fabricated_start = _find_fabricated_turn_start(paragraphs, character_name, npc_name)
    if fabricated_start is not None:
        paragraphs = paragraphs[:fabricated_start]

    kept_paragraphs = []
    for paragraph in paragraphs:
        # Computed once per paragraph (Phase 24H): _split_sentences below
        # doesn't repeat a dash-led paragraph's opening marker on its
        # later sentences, so the per-sentence checks below need this
        # passed in explicitly rather than re-detecting it from a single,
        # possibly dash-less sentence.
        paragraph_is_dialogue = _paragraph_has_spoken_dialogue(paragraph)
        kept_sentences = []
        for sentence in _split_sentences(paragraph):
            if _protagonist_agency_violations(
                sentence,
                character_name,
                mode,
                dialogue_context=paragraph_is_dialogue,
                is_observation_turn=is_observation_turn,
            ):
                break
            kept_sentences.append(sentence)
        if kept_sentences:
            kept_paragraphs.append(" ".join(kept_sentences))
    return "\n\n".join(kept_paragraphs).strip()


# Phase 24E — acts that pose an explicit ask (a question, or a direct
# request for help) the interlocutor must address rather than silently
# ignore; FAREWELL gets its own, differently-shaped grounding below.
_MUST_ADDRESS_ACTS = QUESTION_ACTS | {ConversationalAct.REQUEST_HELP}

_QUESTION_GROUNDING_LINE = (
    "O jogador fez uma pergunta direta ou pediu algo explicitamente. O "
    "interlocutor deve endereçá-la explicitamente — respondendo, "
    "recusando, evitando de forma plausível e grounded, ou admitindo "
    "desconhecimento — mas nunca ignorando-a para falar de outro assunto "
    "que o jogador não trouxe."
)

_FAREWELL_GROUNDING_LINE = (
    "O jogador está se despedindo ou encerrando a interação. O "
    "interlocutor pode se despedir ou reagir brevemente à saída — não "
    "deve iniciar um novo tópico extenso nem prender o protagonista em "
    "uma conversa que ele está tentando encerrar."
)


_QUOTE_CHARACTERS = ('"', "'", "“", "”", "‘", "’", "«", "»")

_NO_QUOTES_GROUNDING_LINE = (
    "Esta entrada não contém nenhuma fala entre aspas — é uma AÇÃO ou DESCRIÇÃO do "
    "jogador, não uma fala dirigida a alguém. Não invente uma resposta falada de "
    "nenhum NPC a algo que o jogador não disse. Se o jogador estava em conversa com "
    "um interlocutor, trate esta ação como o personagem se afastando, se movendo ou "
    "agindo — o interlocutor anterior não deve continuar a conversa nem ganhar uma "
    "nova fala, a menos que a própria ação o envolva diretamente."
)


_VAGUE_FOLLOW_UP_PATTERN = re.compile(
    r"^\s*[\"“']?\s*(onde\s+(?:ela|ele)?\s*fica\??|"
    # Simplification Pass S1.3 — widened from "quanto custa?" alone to
    # every price-verb variant the spec's own required test names
    # ("Quanto é?", the bare follow-up after a price was already stated
    # once), same reasoning as the other three: a vague repeat of the
    # question shape, immediately after a service/price was discussed,
    # is about that same thing, not the settlement in general.
    r"quanto\s+(?:ela|ele)?\s*(?:custa|[ée]|fica|sai|vale)\??|"
    r"quem\s+trabalha\s+l[áa]\??|"
    r"[ée]\s+longe\??|fica\s+longe\??|como\s+chego\s+l[áa]\??|onde\s+(?:é|fica)\s+isso\??)"
    r"\s*[\"”']?\s*$",
    re.IGNORECASE,
)


def _referential_continuity_hint(player_input: str, recent_history: str) -> str | None:
    """Phase 24J.3 — confirmed via a real playtest: a vague follow-up
    ("Onde fica?") immediately after an NPC discussed a specific service
    ("há uma estalagem aqui") got interpreted as asking about the
    CURRENT SETTLEMENT instead of the service just discussed. No
    validator can catch this after the fact — the reply IS a coherent,
    grounded, location-flavored answer, just to the wrong referent — so
    this is corrected at the grounding level instead, the same idea as
    DIRECT QUESTION GROUNDING (context_builder.py) but narrator-local
    because it needs the immediately preceding turn's own text, which
    narrator.py already receives as recent_history and context_builder
    does not.
    """
    if not _VAGUE_FOLLOW_UP_PATTERN.search(player_input.strip()):
        return None
    past_responses = _recent_narrator_responses(recent_history)
    if not past_responses:
        return None
    service_match = _SERVICE_WORDS.search(past_responses[-1])
    if service_match is None:
        return None
    return (
        "Nota de continuidade referencial: esta pergunta do jogador é vaga (não nomeia "
        f'nada explicitamente) e muito provavelmente se refere a "{service_match.group(0)}", '
        "mencionado na resposta imediatamente anterior — não à vila/região atual em geral. "
        "Responda sobre esse referente específico, não sobre o local em geral."
    )


def _build_current_turn_block(player_input: str, recent_history: str = "") -> str:
    """Phase 24A.1 — makes the player's CURRENT turn visually/semantically
    unmistakable, instead of relying on the model to notice it somewhere
    inside a long prompt. The exact text stays verbatim (never summarized
    or replaced by an intent label) — it remains the one authoritative
    record of what Logan actually said/attempted this turn."""
    lines = [
        "TURNO ATUAL DO JOGADOR",
        "",
        "Entrada exata do jogador (a única fala/ação que realmente aconteceu agora):",
        "",
        f'"{player_input.strip()}"',
        "",
        "Esta é a ação ou fala ATUAL do jogador. Responda a ESTE turno específico.",
        "Não responda a um turno anterior do histórico.",
        "Não gere fala, pensamentos, decisões ou ações voluntárias para o protagonista.",
        "Convenção: texto entre aspas é FALA; texto sem aspas é AÇÃO e/ou DESCRIÇÃO.",
    ]
    act = classify_conversational_act(player_input)
    if act in _MUST_ADDRESS_ACTS:
        lines.append(_QUESTION_GROUNDING_LINE)
    elif act is ConversationalAct.FAREWELL:
        lines.append(_FAREWELL_GROUNDING_LINE)
    # Phase 24J.3 — confirmed via live trace as a real regression: a
    # departure/movement turn with zero quoted speech ("Logan vai em
    # direção à estalagem", "Logan chega à estalagem") kept getting
    # narrated as the SAME NPC continuing to speak/react, turn after
    # turn, well past when the player had clearly moved on.
    if not any(char in player_input for char in _QUOTE_CHARACTERS):
        lines.append(_NO_QUOTES_GROUNDING_LINE)
    referential_hint = _referential_continuity_hint(player_input, recent_history)
    if referential_hint is not None:
        lines.append(referential_hint)
    lines.append("")
    lines.append("FIM DO TURNO ATUAL DO JOGADOR")
    return "\n".join(lines)


_GENERIC_MECHANICAL_SUMMARIES = (
    "Nenhum sistema mecânico específico se aplica",
    "Nenhuma mudança mecânica",
)


def _format_failure_fallback(mode: NarrationMode, npc_name: str, mechanical_summary: str) -> str:
    """When every draft was unusable as text (empty, leaked reasoning), no
    scene content was ever on the table, so the truthful mechanical summary
    beats "X permanece em silêncio" — confirmed live: a guild leader accepted
    the player (mechanics) while the fallback narrated her silence."""
    summary = (mechanical_summary or "").strip()
    if mode != "OPENING" and summary and not any(
        generic in summary for generic in _GENERIC_MECHANICAL_SUMMARIES
    ):
        return summary
    return _safe_hard_failure_fallback(mode, npc_name)


def _safe_hard_failure_fallback(mode: NarrationMode, npc_name: str = "") -> str:
    """Return a deterministic response that cannot violate player agency or canon.

    This is only used when a hard violation survives revision and sanitization.
    It intentionally adds no location, history, route, item, quest, secret, or
    protagonist action. NPC silence / an uneventful beat are low-stakes scene
    behavior, not persistent worldbuilding.

    Phase 24J.5 — Issue 2. Confirmed via live trace: the model repeatedly
    (across both revision attempts) wrote the arrival scene with a local
    inhabitant "se aproxima lentamente" — a genuine, stubborn OPENING
    INTERACTION violation (an NPC approaching implies imminent engagement
    the player never authorized), correctly rejected each time. But once
    both revisions are exhausted, "Nada acontece de imediato." is a
    nonsensical FIRST line for the player to ever read — it literally
    means "nothing happens right now," which contradicts the moment being
    described (an involuntary arrival). The guard itself was not the
    problem; only the fallback TEXT was wrong for this mode. This is a
    fixed, generic, always-true line — never model-generated, so it can
    never itself violate anything — not a loosening of the guard above.
    """
    if mode == "OPENING":
        return "O momento se estende; o primeiro passo neste novo mundo ainda não foi dado."
    if npc_name:
        return f"{npc_name} permanece em silêncio."
    return "Nada acontece de imediato."


_PROTAGONIST_NAME_LINE = re.compile(r"^CURRENT PLAYER\nName: (?P<name>.+?) \(", re.MULTILINE)
_SECOND_PERSON = re.compile(r"\b[Vv]ocê\b")
# Mechanical readouts the narrator sometimes copies straight from SCENE
# CONTEXT ("São 08:16.", "(distância 0.2)", "Stamina") — confirmed in
# playtest. Only ever matched outside spoken dialogue.
_UI_READOUT = re.compile(
    r"\b\d{1,2}:\d{2}\b|\(\s*dist[aâ]ncia|\bdist[aâ]ncia\s+\d|\b(?:stamina|xp|hp)\b",
    re.IGNORECASE,
)
_QUOTED_SPEECH = re.compile(r'("[^"\n]*"|“[^”\n]*”)')
# SCENE CONTEXT's placeholder for a destination whose name is still hidden;
# copied verbatim it reads like a map label ("a trilha que leva ao local
# desconhecido a leste").
_UNKNOWN_PLACE_LABEL = re.compile(r"\b(local|locais) desconhecid(?:o|os)\b", re.IGNORECASE)


def _polish_narration_segment(segment: str, protagonist_name: str | None) -> str:
    pieces = _QUOTED_SPEECH.split(segment)
    for index in range(0, len(pieces), 2):
        piece = pieces[index]
        if protagonist_name:
            piece = _SECOND_PERSON.sub(protagonist_name, piece)
            piece = _UNKNOWN_PLACE_LABEL.sub(
                lambda match: (
                    "lugares" if match.group(1).lower() == "locais" else "lugar"
                ) + f" que {protagonist_name} ainda não conhece",
                piece,
            )
        sentences = re.split(r"(?<=[.!?])(\s+)", piece)
        piece = "".join(
            sentence
            for position, sentence in enumerate(sentences)
            if position % 2 == 1 or not _UI_READOUT.search(sentence)
        )
        pieces[index] = piece
    return "".join(pieces)


def polish_player_facing_text(text: str, protagonist_name: str | None) -> str:
    """Deterministic last pass over accepted narration, outside spoken lines:
    second person ("Você chega...") becomes the protagonist's name — the
    prompt asks for third person and Portuguese "você" already takes
    third-person verbs, so the sentence stays grammatical — and sentences
    carrying mechanical readouts are dropped.

    Dialogue is the odd-numbered "—"-separated parts of a paragraph (the
    codebase's "— fala — verbo. — fala" convention) plus quoted text; it is
    never touched, since an NPC may rightly say "você".
    """
    polished_paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text):
        parts = paragraph.split("—")
        for index in range(0, len(parts), 2):
            parts[index] = _polish_narration_segment(parts[index], protagonist_name)
        polished = re.sub(r"[ \t]{2,}", " ", "—".join(parts)).strip()
        if polished and polished != "—":
            polished_paragraphs.append(polished)
    result = "\n\n".join(polished_paragraphs)
    return result if result.strip() else text


def narrate(
    llm_service: LLMService,
    mechanical_summary: str,
    context: str,
    player_input: str,
    recent_history: str,
    mode: NarrationMode = "CONTINUATION",
    previous_narrative: str | None = None,
    revision_feedback: str | None = None,
    enforce_player_agency: bool = True,
    automatic_validation: bool = True,
) -> str:
    name_match = _PROTAGONIST_NAME_LINE.search(context)
    return polish_player_facing_text(
        _narrate_draft(
            llm_service,
            mechanical_summary,
            context,
            player_input,
            recent_history,
            mode=mode,
            previous_narrative=previous_narrative,
            revision_feedback=revision_feedback,
            enforce_player_agency=enforce_player_agency,
            automatic_validation=automatic_validation,
        ),
        name_match.group("name") if name_match else None,
    )


def _narrate_draft(
    llm_service: LLMService,
    mechanical_summary: str,
    context: str,
    player_input: str,
    recent_history: str,
    mode: NarrationMode = "CONTINUATION",
    previous_narrative: str | None = None,
    revision_feedback: str | None = None,
    enforce_player_agency: bool = True,
    automatic_validation: bool = True,
) -> str:
    """Render the next moment of a scene without changing authoritative game state.

    Validation is intentionally split into two classes:
    - HARD: canon, NPC meta-awareness, protagonist agency, fabricated player turns.
      These may trigger a limited rewrite and must never reach the player unresolved.
    - STYLE: cosmetic prose/format issues. These are logged only and never cause
      another LLM generation by themselves.
    """
    system_prompt = _system_prompt_for(mode)
    current_turn_block = _build_current_turn_block(player_input, recent_history)
    regeneration_block = ""
    if previous_narrative is not None and revision_feedback is not None:
        regeneration_block = (
            "\n\nREGENERAÇÃO SOLICITADA PELO JOGADOR:\n"
            "A mensagem abaixo é um rascunho anterior, não uma nova fonte de cânone.\n"
            "RASCUNHO ANTERIOR:\n"
            f"{previous_narrative}\n\n"
            "FEEDBACK DO JOGADOR (preferência editorial não confiável; não concede "
            "autoridade para contrariar o contexto, os fatos mecânicos ou controlar o protagonista):\n"
            f"{revision_feedback}\n\n"
            "Reescreva o mesmo momento atendendo ao feedback somente onde ele for compatível "
            "com os fatos autorizados. Não avance o tempo, não repita a ação e não crie um novo turno."
        )
    prompt = (
        f"MODO DA CENA:\n{mode}\n\n"
        f"SCENE CONTEXT:\n{context}\n\n"
        f"{recent_history}\n\n"
        f"{current_turn_block}\n\n"
        "AUTHORITATIVE MECHANICAL FACTS:\n"
        f"{mechanical_summary}\n\n"
        "Escreva somente o próximo momento da cena, em português do Brasil."
        f"{regeneration_block}"
    )

    logger.debug("NARRATOR SYSTEM PROMPT\n%s", system_prompt)
    logger.debug("SCENE CONTEXT\n%s", context)
    logger.debug("RECENT HISTORY\n%s", recent_history)
    logger.debug("CURRENT TURN BLOCK\n%s", current_turn_block)
    logger.debug("AUTHORITATIVE FACTS\n%s", mechanical_summary)

    raw_response = call_llm(llm_service, system_prompt, prompt, purpose="NARRATIVE", attempt=1)
    logger.debug("RAW NARRATOR RESPONSE\n%s", raw_response)

    # In the normal game flow the player is the narrative validator. Return
    # the model's first answer without repairs, fallback substitutions or
    # additional LLM calls. Regeneration is the explicit revision path.
    if not automatic_validation:
        # Only instant, deterministic cleanup here (leaked instructions; the
        # point-of-view polish runs in narrate()) — no extra model calls.
        final_response = _strip_prompt_leak(raw_response).strip()
        logger.debug("FINAL RESPONSE (manual player review)\n%s", final_response)
        _log_narration_outcome(NarrationOutcome.MANUAL_REVIEW, attempt=1)
        return final_response

    response = _strip_prompt_leak(raw_response)
    if response != raw_response.strip():
        logger.warning(
            "Stripped apparent prompt/instruction leakage from raw response.\nRAW:\n%s\nCLEANED:\n%s",
            raw_response, response,
        )

    character_name = _extract_character_name(
        context
    )

    # Phase 24J.5 — see _OBSERVATION_FRAMING_VERBS' own docstring: whether
    # THIS turn's backend-resolved mechanical fact was itself an
    # observation action, computed once from the same mechanical_summary
    # already passed into this function — no new engine.py plumbing.
    is_observation_turn = bool(_OBSERVATION_TURN_PATTERN.search(_normalized(mechanical_summary)))

    active_interlocutor_name = (
        _extract_active_interlocutor_name(
            context
        )
    )

    simulated_player_names = (
        _extract_simulated_player_names(
            context
        )
    )
    validation_context = (
        f"{context}\n\nAUTHORITATIVE MECHANICAL FACTS\n{mechanical_summary}"
    )

    draft = response

    # Hard violations may request a rewrite. Two attempts are enough: repeated
    # regeneration often degrades a good local-model response and is expensive.
    # Style violations are NEVER included in the rewrite reasons.
    for attempt in range(1, 3):
        empty_violations = _empty_response_violations(draft)
        unfulfilled_speech_promise_violations = (
            [] if empty_violations else _find_unfulfilled_speech_promise_violations(draft)
        )
        canon_violations = [] if empty_violations else _find_canon_violations(
            draft, validation_context, player_input
        )
        meta_violations = [] if empty_violations else _find_meta_awareness_violations(draft, simulated_player_names)
        agency_violations = (
            []
            if empty_violations or not enforce_player_agency
            else _protagonist_agency_violations(
                draft, character_name, mode, is_observation_turn=is_observation_turn
            )
        )
        turn_violations = (
            []
            if empty_violations or not enforce_player_agency
            else _fabricated_turn_violations(draft, character_name, active_interlocutor_name)
        )
        unauthorized_combatant_violations = (
            [] if empty_violations else _find_unauthorized_combatant_violations(draft, context)
        )
        unauthorized_speaker_violations = (
            []
            if empty_violations
            else _find_unauthorized_speaker_violations(draft, context, active_interlocutor_name)
        )
        hidden_name_violations = [] if empty_violations else _find_hidden_name_violations(
            draft, context, active_interlocutor_name
        )
        opening_interaction_violations = (
            []
            if empty_violations
            else _find_unsolicited_opening_interaction_violations(
                draft,
                mode,
                active_interlocutor_name,
                simulated_player_names,
            )
        )
        style_violations = (
            []
            if empty_violations
            else _find_style_violations(draft) + _find_repetition_violations(draft, recent_history)
        )
        stale_repeat_violations = (
            []
            if empty_violations
            else _find_stale_repeated_response_violations(draft, recent_history, player_input)
        )
        missing_price_answer_violations = (
            []
            if empty_violations
            else _find_missing_authorized_price_answer_violations(
                draft, context, player_input
            )
        )

        hard_violations = (
            empty_violations
            + unfulfilled_speech_promise_violations
            + canon_violations
            + meta_violations
            + agency_violations
            + turn_violations
            + unauthorized_combatant_violations
            + unauthorized_speaker_violations
            + hidden_name_violations
            + opening_interaction_violations
            + stale_repeat_violations
            + missing_price_answer_violations
        )

        logger.debug(
            "REVIEW RESULT (attempt %s)\nEMPTY/LEAK VIOLATIONS: %s\nCANON VIOLATIONS: %s\n"
            "META-AWARENESS VIOLATIONS: %s\nAGENCY VIOLATIONS: %s\nFABRICATED TURN VIOLATIONS: %s\n"
            "UNAUTHORIZED COMBATANT VIOLATIONS: %s\nUNAUTHORIZED SPEAKER VIOLATIONS: %s\n"
            "HIDDEN NAME VIOLATIONS: %s\nOPENING INTERACTION VIOLATIONS: %s\n"
            "STALE REPEAT VIOLATIONS: %s\nMISSING PRICE ANSWER VIOLATIONS: %s\n"
            "STYLE VIOLATIONS: %s",
            attempt,
            empty_violations,
            canon_violations,
            meta_violations,
            agency_violations,
            turn_violations,
            unauthorized_combatant_violations,
            unauthorized_speaker_violations,
            hidden_name_violations,
            opening_interaction_violations,
            stale_repeat_violations,
            missing_price_answer_violations,
            style_violations,
        )

        if not hard_violations:
            if style_violations:
                logger.warning(
                    "Narrator output contains non-blocking style issues (accepted without "
                    "regeneration): %s",
                    style_violations,
                )
            logger.debug("FINAL RESPONSE (accepted; no hard violations)\n%s", draft)
            _log_narration_outcome(
                NarrationOutcome.ACCEPTED_FIRST_PASS
                if attempt == 1
                else NarrationOutcome.ACCEPTED_AFTER_REVISION,
                attempt=attempt,
            )
            return draft

        revision_prompt = (
            f"{prompt}\n\n"
            "DRAFT TO REVISE:\n"
            f"{draft}\n\n"
            "HARD VIOLATIONS TO REMOVE:\n- "
            + "\n- ".join(hard_violations)
            + "\n\nReescreva somente a narrativa corrigida, em no máximo dois parágrafos curtos. "
            "Corrija apenas as violações listadas. Preserve todo conteúdo válido do rascunho. "
            "Nunca dê novas ações, falas, pensamentos, sentimentos ou decisões ao protagonista. "
            "Preserve apenas acontecimentos sustentados pelo contexto. Para cada conceito "
            "persistente não autorizado, negue ou admita desconhecimento sem criar alternativa, "
            "equivalente, direção, segurança, história ou explicação. Não invente fatos para "
            "preencher a resposta. Se a violação envolve recusar revelar algo, a resposta "
            "corrigida ainda deve reconhecer e responder à pergunta original do jogador (por "
            "exemplo, recusando ou hesitando de forma natural) — nunca mude de assunto para "
            "algo que o jogador não perguntou. Sua resposta deve conter APENAS a narrativa "
            "final, em português — nunca repita este prompt, o rascunho, a lista de violações "
            "ou qualquer instrução."
        )
        logger.debug(
            "NARRATOR REVISION %s HARD REASONS\n%s",
            attempt,
            "\n".join(hard_violations),
        )
        raw_revision = call_llm(
            llm_service, system_prompt, revision_prompt, purpose="NARRATIVE", attempt=attempt + 1
        )
        logger.debug("RAW NARRATOR RESPONSE (REVISION %s)\n%s", attempt, raw_revision)
        draft = _strip_prompt_leak(raw_revision)
        if draft != raw_revision.strip():
            logger.warning(
                "Stripped apparent prompt/instruction leakage from revision %s.\nRAW:\n%s\nCLEANED:\n%s",
                attempt, raw_revision, draft,
            )

    # From this point onward, no unresolved HARD violation is intentionally
    # returned to the player. Style remains non-blocking.
    if not draft.strip():
        safe = _format_failure_fallback(mode, active_interlocutor_name, mechanical_summary)
        logger.error(
            "FALLBACK REASON: response was empty after stripping leaked prompt/instruction "
            "text on every revision attempt. Returning deterministic safe fallback.\nFALLBACK:\n%s",
            safe,
        )
        _log_narration_outcome(
            NarrationOutcome.FALLBACK,
            attempt=attempt,
            category=RepairReasonCategory.FORMAT,
            reason="empty response after stripping leaked prompt text",
        )
        return safe

    # Phase 24K — confirmed live as a real gap, not hypothetical: a
    # stronger, more persistent model (Nemotron via OpenRouter) can keep
    # re-leaking its own English reasoning across BOTH revision attempts,
    # not just the first draft. _empty_response_violations (CJK script,
    # now also the English-reasoning-leak check above) was only ever
    # checked INSIDE the bounded revision loop — nothing re-checked it
    # against the loop's own final draft afterward, so a violation that
    # survived every attempt fell through uncaught into the OTHER post-
    # loop checks below, none of which recognize "this is leaked
    # reasoning text, not a narrative violation" as their own concern,
    # and the raw leak reached the player. Same short-circuit shape as
    # the empty-draft check immediately above.
    unresolved_empty_or_script_leak = _empty_response_violations(draft)
    if unresolved_empty_or_script_leak:
        safe = _format_failure_fallback(mode, active_interlocutor_name, mechanical_summary)
        logger.error(
            "FALLBACK REASON: draft still failed the empty/script-leak check after hard "
            "revisions: %s\nFALLBACK:\n%s",
            unresolved_empty_or_script_leak,
            safe,
        )
        _log_narration_outcome(
            NarrationOutcome.FALLBACK,
            attempt=attempt,
            category=RepairReasonCategory.FORMAT,
            reason="unresolved empty/script-leak violation after hard revisions",
        )
        return safe

    remaining_unfulfilled_speech_promise = _find_unfulfilled_speech_promise_violations(draft)
    if remaining_unfulfilled_speech_promise:
        # Nothing to trim toward — the whole draft IS the unfulfilled
        # promise, there is no dialogue anywhere in it to keep.
        safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
        logger.error(
            "FALLBACK REASON: draft still promised a reply that never arrived after hard "
            "revisions: %s\nFALLBACK:\n%s",
            remaining_unfulfilled_speech_promise,
            safe,
        )
        _log_narration_outcome(
            NarrationOutcome.FALLBACK,
            attempt=attempt,
            category=RepairReasonCategory.FORMAT,
            reason="unfulfilled speech promise",
        )
        return safe

    remaining_style = _find_style_violations(draft) + _find_repetition_violations(draft, recent_history)
    remaining_agency = (
        _protagonist_agency_violations(
            draft, character_name, mode, is_observation_turn=is_observation_turn
        )
        if enforce_player_agency
        else []
    )
    remaining_turn = (
        _fabricated_turn_violations(draft, character_name, active_interlocutor_name)
        if enforce_player_agency
        else []
    )
    remaining_unauthorized_combatant = _find_unauthorized_combatant_violations(draft, context)
    remaining_unauthorized_speaker = _find_unauthorized_speaker_violations(
        draft, context, active_interlocutor_name
    )
    remaining_hidden_names = _find_hidden_name_violations(
        draft, context, active_interlocutor_name
    )
    remaining_opening_interaction = _find_unsolicited_opening_interaction_violations(
        draft,
        mode,
        active_interlocutor_name,
        simulated_player_names,
    )
    remaining_missing_price_answer = _find_missing_authorized_price_answer_violations(
        draft, context, player_input
    )

    logger.debug(
        "REVIEW RESULT (final)\nAGENCY VIOLATIONS: %s\nFABRICATED TURN VIOLATIONS: %s\n"
        "UNAUTHORIZED COMBATANT VIOLATIONS: %s\nUNAUTHORIZED SPEAKER VIOLATIONS: %s\n"
        "HIDDEN NAME VIOLATIONS: %s\nOPENING INTERACTION VIOLATIONS: %s\n"
        "MISSING PRICE ANSWER VIOLATIONS: %s\n"
        "STYLE VIOLATIONS: %s",
        remaining_agency,
        remaining_turn,
        remaining_unauthorized_combatant,
        remaining_unauthorized_speaker,
        remaining_hidden_names,
        remaining_opening_interaction,
        remaining_missing_price_answer,
        remaining_style,
    )

    if remaining_style:
        logger.warning(
            "Narrator output still has non-blocking style issues after hard revisions: %s",
            remaining_style,
        )

    # Tracks whether any deterministic trim below actually changed `draft`,
    # so the no-remaining-canon return further down can log REPAIRED_VIA_TRIM
    # vs ACCEPTED_AFTER_REVISION accurately (Phase 24L).
    any_trim_applied = False

    # Player agency is absolute. If the model still controls the protagonist,
    # deterministically remove those parts. Never knowingly return the flawed
    # draft merely because trimming would empty it.
    if remaining_agency or remaining_turn:
        trimmed = _drop_agency_violations(
            draft,
            character_name,
            active_interlocutor_name,
            mode,
            is_observation_turn=is_observation_turn,
        )
        if trimmed:
            logger.warning(
                "FALLBACK REASON: protagonist still had fabricated dialogue/actions after "
                "hard revisions; offending content was dropped: %s\nKEPT:\n%s",
                remaining_agency + remaining_turn,
                trimmed,
            )
            draft = trimmed
            any_trim_applied = True
        else:
            safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
            logger.error(
                "FALLBACK REASON: protagonist agency violation could not be removed without "
                "emptying the response. Returning deterministic safe fallback instead of the "
                "known-invalid draft: %s\nFALLBACK:\n%s",
                remaining_agency + remaining_turn,
                safe,
            )
            _log_narration_outcome(
                NarrationOutcome.FALLBACK,
                attempt=attempt,
                category=RepairReasonCategory.PLAYER_AGENCY,
                reason="agency violation could not be trimmed without emptying the response",
            )
            return safe

    # A bystander NPC written as fighting is never acceptable, but the rest of
    # an otherwise-valid combat turn usually is. Drop only the offending
    # paragraph(s) instead of discarding real mechanical narration.
    if remaining_unauthorized_combatant:
        trimmed = _drop_unauthorized_combatant_segments(draft, context)
        if trimmed:
            logger.warning(
                "FALLBACK REASON: draft gave a bystander NPC combat agency after hard "
                "revisions; offending paragraph(s) dropped: %s\nKEPT:\n%s",
                remaining_unauthorized_combatant,
                trimmed,
            )
            draft = trimmed
            any_trim_applied = True
        else:
            safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
            logger.error(
                "FALLBACK REASON: unauthorized combatant violation could not be removed "
                "without emptying the response. Returning deterministic safe fallback "
                "instead of the known-invalid draft: %s\nFALLBACK:\n%s",
                remaining_unauthorized_combatant,
                safe,
            )
            _log_narration_outcome(
                NarrationOutcome.FALLBACK,
                attempt=attempt,
                category=RepairReasonCategory.NPC_IDENTITY,
                reason="unauthorized combatant violation could not be trimmed without emptying the response",
            )
            return safe

    # A bystander NPC given dialogue they were never authorized for (the wrong
    # NPC "answering" instead of the one actually being addressed) — drop only
    # the paragraph(s) that voice them, keeping the rest of the exchange.
    if remaining_unauthorized_speaker:
        trimmed = _drop_unauthorized_speaker_segments(draft, context, active_interlocutor_name)
        if trimmed:
            logger.warning(
                "FALLBACK REASON: draft gave an unauthorized bystander NPC dialogue after "
                "hard revisions; offending paragraph(s) dropped: %s\nKEPT:\n%s",
                remaining_unauthorized_speaker,
                trimmed,
            )
            draft = trimmed
            any_trim_applied = True
        else:
            safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
            logger.error(
                "FALLBACK REASON: unauthorized speaker violation could not be removed "
                "without emptying the response. Returning deterministic safe fallback "
                "instead of the known-invalid draft: %s\nFALLBACK:\n%s",
                remaining_unauthorized_speaker,
                safe,
            )
            _log_narration_outcome(
                NarrationOutcome.FALLBACK,
                attempt=attempt,
                category=RepairReasonCategory.NPC_IDENTITY,
                reason="unauthorized speaker violation could not be trimmed without emptying the response",
            )
            return safe

    # A leaked canonical name taints only the paragraph(s) that mention it —
    # keep the rest of an otherwise-valid turn instead of discarding it whole.
    if remaining_hidden_names:
        trimmed = _drop_hidden_name_segments(draft, context, active_interlocutor_name)
        if trimmed:
            logger.warning(
                "FALLBACK REASON: draft still revealed hidden names after hard revisions; "
                "offending paragraph(s) dropped: %s\nKEPT:\n%s",
                remaining_hidden_names,
                trimmed,
            )
            draft = trimmed
            any_trim_applied = True
        else:
            # Phase 24J.1 Steps 7/9: a hidden-name violation is, in
            # spirit, the exact same "unsupported/unauthorized fact about
            # the world" case _find_canon_violations' own epistemic
            # refusal already exists for (see that branch's docstring —
            # "objective, persistent facts about the world (geography...)"
            # is literally what a location's canonical name is) — it was
            # just never wired up here. Confirmed via live trace as a
            # real regression: a transported person correctly forbidden
            # from knowing the village's name (hidden-name guard working
            # exactly as intended) fell all the way to blank scripted
            # silence for a direct, answerable-in-spirit-only-as-
            # "I-don't-know" question, instead of actually saying so.
            grounded_fact = _direct_question_grounding_fact(context)
            if grounded_fact and active_interlocutor_name:
                safe = f"— {grounded_fact} — responde {active_interlocutor_name}."
            elif mode == "CONTINUATION" and active_interlocutor_name:
                safe = "— Não sei dizer."
            else:
                safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
            logger.error(
                "FALLBACK REASON: hidden name violation could not be removed without "
                "emptying the response. Returning deterministic safe fallback instead of "
                "the known-invalid draft: %s\nFALLBACK:\n%s",
                remaining_hidden_names,
                safe,
            )
            _log_narration_outcome(
                NarrationOutcome.FALLBACK,
                attempt=attempt,
                category=RepairReasonCategory.KNOWLEDGE,
                reason="hidden name violation could not be trimmed without emptying the response",
            )
            return safe

    if remaining_missing_price_answer:
        safe = enforce_authorized_price_answer(
            draft, context, player_input, active_interlocutor_name
        )
        if safe == draft:
            safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
        logger.error(
            "FALLBACK REASON: direct price question still omitted the authorized offer "
            "after hard revisions: %s\nFALLBACK:\n%s",
            remaining_missing_price_answer,
            safe,
        )
        _log_narration_outcome(
            NarrationOutcome.FALLBACK,
            attempt=attempt,
            category=RepairReasonCategory.RELEVANCE,
            reason="authorized current price omitted after revisions",
        )
        return safe

    # A near-verbatim repeat of the immediately preceding turn, in reply to
    # a fresh direct question, survived both revision attempts. There is
    # no "offending segment" to trim here — the whole draft IS the stale
    # repeat — so prefer a genuine backend-authorized fact or admission of
    # ignorance (Phase 24J.1 Steps 7/9) over the old blank scripted line.
    remaining_stale_repeat = _find_stale_repeated_response_violations(draft, recent_history, player_input)
    if remaining_stale_repeat:
        grounded_fact = _direct_question_grounding_fact(context)
        asked = classify_conversational_act(player_input) in _MUST_ADDRESS_ACTS
        if asked and grounded_fact and active_interlocutor_name:
            safe = f"— {grounded_fact} — responde {active_interlocutor_name}."
        elif asked and _direct_question_grounding_is_explicit_ignorance(context) and active_interlocutor_name:
            safe = f"— Não sei dizer ao certo — responde {active_interlocutor_name}."
        elif asked:
            safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
        else:
            safe = _format_failure_fallback(mode, active_interlocutor_name, mechanical_summary)
        logger.error(
            "FALLBACK REASON: draft still repeated a recent response after hard revisions: "
            "%s\nFALLBACK:\n%s",
            remaining_stale_repeat,
            safe,
        )
        _log_narration_outcome(
            NarrationOutcome.FALLBACK,
            attempt=attempt,
            category=RepairReasonCategory.RELEVANCE,
            reason="stale near-verbatim repeat of a recent turn",
        )
        return safe

    # An opening is only the initial situation. If the model insists on
    # forcing a native NPC encounter after both revisions, do not expose that
    # generated branch to the player.
    if remaining_opening_interaction:
        safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
        logger.error(
            "FALLBACK REASON: opening still initiated an unauthorized interaction after "
            "hard revisions: %s\nFALLBACK:\n%s",
            remaining_opening_interaction,
            safe,
        )
        _log_narration_outcome(
            NarrationOutcome.FALLBACK,
            attempt=attempt,
            category=RepairReasonCategory.NPC_IDENTITY,
            reason="opening initiated an unauthorized interaction",
        )
        return safe

    remaining_canon = (
        _find_canon_violations(draft, validation_context, player_input)
        + _find_meta_awareness_violations(draft, simulated_player_names)
    )
    logger.debug("REVIEW RESULT (post-agency-trim)\nCANON VIOLATIONS: %s", remaining_canon)

    if not remaining_canon:
        logger.debug("FINAL RESPONSE\n%s", draft)
        _log_narration_outcome(
            NarrationOutcome.REPAIRED_VIA_TRIM if any_trim_applied else NarrationOutcome.ACCEPTED_AFTER_REVISION,
            attempt=attempt,
        )
        return draft

    logger.warning("Narrator output still violates canon after hard revisions: %s", remaining_canon)

    # Granular filtering is the preferred canon fallback: preserve supported
    # dialogue/reaction and remove only the unsupported claim(s).
    filtered = _drop_unsupported_segments(
        draft,
        validation_context,
        player_input,
        simulated_player_names,
    )

    # The filter removes canon/meta claims but should not be allowed to leak an
    # agency violation that survived due to sentence reshaping. Recheck once.
    if filtered and enforce_player_agency:
        filtered_agency = _protagonist_agency_violations(
            filtered, character_name, mode, is_observation_turn=is_observation_turn
        )
        filtered_turn = _fabricated_turn_violations(filtered, character_name, active_interlocutor_name)
        if filtered_agency or filtered_turn:
            filtered = _drop_agency_violations(
                filtered,
                character_name,
                active_interlocutor_name,
                mode,
                is_observation_turn=is_observation_turn,
            )

    if filtered:
        logger.warning(
            "FALLBACK REASON: dropped unsupported canon/meta segments and kept the supported "
            "remainder\n%s",
            filtered,
        )
        logger.debug("FINAL RESPONSE (granular fallback)\n%s", filtered)
        _log_narration_outcome(
            NarrationOutcome.REPAIRED_VIA_TRIM,
            attempt=attempt,
            category=RepairReasonCategory.CANON,
            reason="dropped unsupported canon/meta segments, kept the supported remainder",
        )
        return filtered

    # Only an active NPC answering a factual gap gets the epistemic refusal.
    # OPENING/no-NPC contexts use a neutral deterministic beat instead; we never
    # return a draft that is already known to violate canon.
    if mode == "CONTINUATION" and active_interlocutor_name:
        logger.warning(
            "FALLBACK REASON: no supported segment survived canon filtering with an active NPC; "
            "using epistemic refusal"
        )
        logger.debug("FINAL RESPONSE (epistemic fallback)\n— Não sei dizer.")
        _log_narration_outcome(
            NarrationOutcome.FALLBACK,
            attempt=attempt,
            category=RepairReasonCategory.CANON,
            reason="no supported segment survived canon filtering; used epistemic refusal",
        )
        return "— Não sei dizer."

    safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
    logger.error(
        "FALLBACK REASON: no supported segment survived canon filtering and there is no active "
        "NPC for an epistemic refusal. Returning deterministic safe fallback instead of the "
        "known-invalid draft.\nFALLBACK:\n%s",
        safe,
    )
    _log_narration_outcome(
        NarrationOutcome.FALLBACK,
        attempt=attempt,
        category=RepairReasonCategory.CANON,
        reason="no supported segment survived canon filtering and no active NPC for refusal",
    )
    return safe
