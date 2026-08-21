import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService, LLMServiceError
from app.core.logging import get_logger
from app.db.models.character import Character
from app.db.models.skill import Technique
from app.db.models.technique_evidence import TechniqueExperimentRecord
from app.game.skills.technique_evidence import technique_pattern_maturity
from app.game.skills.techniques import (
    TechniqueRecognitionError,
    recognize_technique_from_pattern,
)

# Phase 11J — LLM Proposal + Backend Validation. The backend gathers and
# owns every mechanical fact; the LLM only ever gives a mature pattern a
# name and a description consistent with what was actually observed. If
# the proposal contradicts the evidence (invents a number, an element not
# practiced, a guaranteed status effect...), the backend rejects it and
# tries again — it never silently accepts or "fixes" a bad proposal itself
# (that would mean the backend inventing identity, which isn't its job
# either).

logger = get_logger("game")

_PROMPT_PATH = Path(__file__).parents[2] / "ai" / "prompts" / "technique_naming_system.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_MAX_ATTEMPTS = 2

_STATUS_EFFECT_TERMS = (
    "atordoa", "atordoado", "atordoante",
    "paralisa", "paralisado", "paralisia",
    "envenena", "envenenado", "veneno",
    "queima", "queimando", "queimadura",
    "sangra", "sangrando", "sangramento",
    "derruba", "derrubado", "derrubar",
    "cega", "cegado", "cegueira",
    "silencia", "silenciado", "silêncio",
    "amedronta", "amedrontado", "medo",
    "explode", "explosão", "explosivo",
    "nocauteia", "nocauteado", "nocaute",
    "nunca erra", "sempre acerta", "garantidamente", "certamente atinge",
)

# A small, curated set of elemental/domain-flavored Portuguese terms the
# proposal must not use unless the matching domain key was actually
# evidenced. Not exhaustive by design (Phase 11H already flags exhaustive
# similarity/vocabulary matching as future work, not to be solved here) —
# this covers the concrete case the spec itself worked through (Wind
# evidence must not become a fire technique).
_ELEMENT_TERMS_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "FIRE": ("fogo", "chama", "flama", "incêndio", "ígneo"),
    "COLD": ("gelo", "congela", "glacial"),
    "ICE": ("gelo", "congela", "glacial"),
    "LIGHTNING": ("raio", "relâmpago", "elétric", "eletrico"),
    "POISON": ("veneno", "tóxic", "toxic"),
    "WIND": ("vento", "rajada", "ventania"),
    "EARTH": ("terra", "pedra", "rocha"),
    "WATER": ("água", "agua", "aquático", "aquatico"),
    "LIGHT": ("luz", "luminos", "radiante"),
    "SHADOW": ("sombra", "trevas", "escuridão", "escuridao"),
}

_NUMERIC_CLAIM_PATTERN = re.compile(
    r"\b\d+([.,]\d+)?\s*"
    r"(de\s+)?"
    r"(dano|cura|mana|estamina|stamina|vida|hp|%|por\s*cento|"
    r"segundos?|turnos?|rodadas?|metros?)\b",
    re.IGNORECASE,
)


class TechniqueNamingError(ValueError):
    pass


@dataclass(frozen=True)
class TechniquePatternEvidenceSummary:
    pattern_key: str
    domain_keys: tuple[str, ...]
    technique_type: str
    depth: float
    evidence_count: int
    resource_key: str | None
    average_resource_cost: float | None
    success_count: int
    partial_count: int
    failure_count: int


@dataclass(frozen=True)
class TechniqueIdentityProposal:
    name: str
    description: str


def gather_technique_pattern_evidence_summary(
    db: Session,
    character_id: str,
    pattern_key: str,
) -> TechniquePatternEvidenceSummary:
    """The authoritative facts an identity proposal may draw on — nothing
    else. Raises if the pattern hasn't actually matured (11C/11G); naming
    an immature or unintegrated pattern is never attempted."""
    maturity = technique_pattern_maturity(db, character_id, pattern_key)
    if not maturity.mature:
        raise TechniqueNamingError(
            "This pattern is not mature enough to gather naming evidence for."
        )
    records = (
        db.query(TechniqueExperimentRecord)
        .filter(
            TechniqueExperimentRecord.character_id == character_id,
            TechniqueExperimentRecord.pattern_key == maturity.pattern_key,
        )
        .all()
    )
    resource_key = records[0].resource_key if records else None
    average_cost = (
        sum(record.resource_cost for record in records) / len(records) if records else None
    )
    return TechniquePatternEvidenceSummary(
        pattern_key=maturity.pattern_key,
        domain_keys=maturity.domain_keys,
        technique_type=maturity.technique_type,
        depth=maturity.depth,
        evidence_count=maturity.evidence_count,
        resource_key=resource_key,
        average_resource_cost=average_cost,
        success_count=sum(1 for r in records if r.outcome == "SUCCESS"),
        partial_count=sum(1 for r in records if r.outcome == "PARTIAL"),
        failure_count=sum(1 for r in records if r.outcome == "FAILURE"),
    )


def _outcome_pattern_label(summary: TechniquePatternEvidenceSummary) -> str:
    total = summary.success_count + summary.partial_count + summary.failure_count
    if total == 0:
        return "resultado ainda não registrado em detalhe"
    if summary.failure_count == 0 and summary.partial_count == 0:
        return "consistentemente bem-sucedido"
    if summary.success_count >= total - summary.success_count:
        return "majoritariamente bem-sucedido, com alguma instabilidade ocasional"
    return "ainda instável, com sucesso apenas parcial na maior parte das tentativas"


def _evidence_summary_text(summary: TechniquePatternEvidenceSummary) -> str:
    lines = [
        f"Domínios: {' + '.join(summary.domain_keys)}",
        f"Tipo: {summary.technique_type}",
    ]
    if summary.resource_key:
        lines.append(f"Recurso usado: {summary.resource_key}")
    lines.append(f"Padrão de resultado: {_outcome_pattern_label(summary)}")
    return "\n".join(lines)


def _request_identity_proposal(
    llm_service: LLMService,
    summary: TechniquePatternEvidenceSummary,
    *,
    previous_violations: list[str] | None = None,
) -> TechniqueIdentityProposal | None:
    prompt = f"Resumo da evidência autoritativa:\n{_evidence_summary_text(summary)}"
    if previous_violations:
        prompt += (
            "\n\nSua proposta anterior violou estas regras — proponha de novo, "
            "corrigindo apenas isso:\n- " + "\n- ".join(previous_violations)
        )
    try:
        raw = llm_service.generate(_SYSTEM_PROMPT, prompt)
    except LLMServiceError:
        logger.info("technique naming: LLM unavailable")
        return None
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("technique naming: could not parse LLM response: %r", raw)
        return None
    name = data.get("name")
    description = data.get("description")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(description, str) or not description.strip():
        return None
    return TechniqueIdentityProposal(name=name.strip(), description=description.strip())


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _validate_identity_proposal(
    proposal: TechniqueIdentityProposal,
    summary: TechniquePatternEvidenceSummary,
) -> list[str]:
    """Reject anything the proposal claims that the evidence doesn't
    support. Deliberately conservative: false positives (rejecting a fine
    proposal) just cost a retry; false negatives would let the LLM define
    mechanical truth, which it must never do."""
    text = f"{proposal.name} {proposal.description}"
    normalized_text = _normalized(text)
    violations = []

    if _NUMERIC_CLAIM_PATTERN.search(text):
        violations.append(
            "a proposta inclui um valor numérico de jogo (dano, custo, duração, "
            "porcentagem); nunca inclua números — isso é decidido pelo backend"
        )

    for term in _STATUS_EFFECT_TERMS:
        if _normalized(term) in normalized_text:
            violations.append(
                f"a proposta menciona um efeito de status ou garantia não observada "
                f"({term!r}); descreva apenas o que o resumo relata"
            )
            break

    for domain_key, terms in _ELEMENT_TERMS_BY_DOMAIN.items():
        if domain_key in summary.domain_keys:
            continue
        for term in terms:
            if _normalized(term) in normalized_text:
                violations.append(
                    f"a proposta menciona {term!r}, associado ao domínio {domain_key}, "
                    "que não está entre os domínios evidenciados "
                    f"({', '.join(summary.domain_keys)})"
                )
                break

    return violations


def propose_and_recognize_technique(
    db: Session,
    campaign_id: str,
    character: Character,
    llm_service: LLMService,
    *,
    pattern_key: str,
) -> Technique | None:
    """The full 11J flow: gather evidence, ask the LLM for identity, validate
    it against that same evidence, and only then persist+grant the
    technique (11C/11H). Returns None (not an exception) when no valid
    proposal could be produced after retrying — the pattern stays mature
    but unnamed, available to try again later, rather than ever persisting
    a technique with an unsupported identity."""
    summary = gather_technique_pattern_evidence_summary(db, character.id, pattern_key)

    violations: list[str] | None = None
    for _attempt in range(_MAX_ATTEMPTS):
        proposal = _request_identity_proposal(
            llm_service, summary, previous_violations=violations
        )
        if proposal is None:
            continue
        violations = _validate_identity_proposal(proposal, summary)
        if not violations:
            try:
                return recognize_technique_from_pattern(
                    db,
                    campaign_id,
                    character,
                    pattern_key=pattern_key,
                    name=proposal.name,
                    description=proposal.description,
                )
            except TechniqueRecognitionError:
                logger.warning(
                    "technique naming: recognition rejected a validated proposal for %s",
                    pattern_key,
                )
                return None
        logger.warning(
            "technique naming: proposal for %s rejected: %s", pattern_key, violations
        )

    logger.warning(
        "technique naming: no valid identity proposal for %s after %s attempts",
        pattern_key,
        _MAX_ATTEMPTS,
    )
    return None
