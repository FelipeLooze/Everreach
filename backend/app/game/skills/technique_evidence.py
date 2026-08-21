import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import DomainEvidenceSource, ProfessionActivityOutcome, TechniqueType
from app.db.models.character import Character
from app.db.models.domain import DomainDefinition
from app.db.models.technique_evidence import (
    CharacterTechniquePatternEvidence,
    TechniquePatternEvidenceRecord,
)
from app.game.domains.service import repetition_multiplier
from app.game.time.clock import get_world_time

# A freeform attempt is not yet a technique. This engine only tracks how
# reproducible one specific attempted maneuver ("pattern_key") has become —
# recognizing it as a real Technique (naming it, persisting it) is later work
# (11I/11J) that consumes technique_pattern_maturity()'s verdict.

TECHNIQUE_PATTERN_EVIDENCE_WINDOW_MINUTES = 24 * 60
TECHNIQUE_RECOGNITION_DEPTH_THRESHOLD = 5.0
TECHNIQUE_RECOGNITION_MIN_EVIDENCE_COUNT = 3
# Kept equal to techniques.MAX_TECHNIQUE_DOMAINS by convention, not import —
# importing it here would create a circular dependency (techniques.py already
# imports from progression.outcomes, which imports this module).
MAX_TECHNIQUE_DOMAINS = 4
_PATTERN_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,179}$")

# A genuine success is worth the full amount; a failed attempt is still real
# practice (per spec: repeated attempts count even when they don't land) but
# worth much less than reproducing the maneuver correctly.
_OUTCOME_MULTIPLIER = {
    ProfessionActivityOutcome.SUCCESS: 1.0,
    ProfessionActivityOutcome.PARTIAL: 0.5,
    ProfessionActivityOutcome.FAILURE: 0.25,
}


class TechniquePatternEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class TechniquePatternEvidenceAward:
    evidence: CharacterTechniquePatternEvidence
    record: TechniquePatternEvidenceRecord
    repetition_multiplier: float


@dataclass(frozen=True)
class TechniquePatternMaturity:
    pattern_key: str
    domain_keys: tuple[str, ...]
    technique_type: str
    depth: float
    evidence_count: int
    mature: bool


def _normalize_pattern_key(pattern_key: str) -> str:
    normalized = pattern_key.strip().lower()
    if not _PATTERN_KEY_PATTERN.fullmatch(normalized):
        raise TechniquePatternEvidenceError("Invalid technique pattern key.")
    return normalized


def _normalize_domain_keys(db: Session, domain_keys: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(sorted({key.strip().upper() for key in domain_keys}))
    if not 1 <= len(normalized) <= MAX_TECHNIQUE_DOMAINS:
        raise TechniquePatternEvidenceError(
            "A technique pattern must involve between one and four domains."
        )
    known = {
        row.key
        for row in db.query(DomainDefinition).filter(DomainDefinition.key.in_(normalized)).all()
    }
    if known != set(normalized):
        raise TechniquePatternEvidenceError("Technique pattern contains an unknown domain.")
    return normalized


def award_technique_pattern_evidence(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    pattern_key: str,
    domain_keys: tuple[str, ...],
    technique_type: TechniqueType,
    source: DomainEvidenceSource,
    outcome: ProfessionActivityOutcome,
    evidence_key: str,
    context_key: str,
    base_amount: float,
) -> TechniquePatternEvidenceAward:
    """Record one attempt at a not-yet-recognized maneuver.

    Anti-farming reuses the exact domain-evidence formula: repeating the same
    (pattern, source, evidence_key) within the window has diminishing
    returns, so varying how/where the maneuver is practiced matters more than
    spamming the identical drill.
    """
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    if not isinstance(source, DomainEvidenceSource):
        raise ValueError("Invalid technique pattern evidence source.")
    if not isinstance(outcome, ProfessionActivityOutcome):
        raise ValueError("Invalid technique pattern attempt outcome.")
    if not isinstance(technique_type, TechniqueType):
        raise ValueError("Invalid technique type.")
    if base_amount <= 0:
        raise ValueError("Technique pattern evidence amount must be positive.")
    if not evidence_key.strip():
        raise ValueError("Technique pattern evidence key is required.")
    if not context_key.strip():
        raise ValueError("Technique pattern evidence context is required.")

    normalized_pattern = _normalize_pattern_key(pattern_key)
    normalized_domains = _normalize_domain_keys(db, domain_keys)
    normalized_domain_field = ",".join(normalized_domains)
    normalized_evidence = evidence_key.strip().lower()
    normalized_context = context_key.strip().lower()

    evidence = (
        db.query(CharacterTechniquePatternEvidence)
        .filter(
            CharacterTechniquePatternEvidence.character_id == character.id,
            CharacterTechniquePatternEvidence.pattern_key == normalized_pattern,
        )
        .first()
    )
    if evidence is not None:
        if evidence.domain_keys != normalized_domain_field:
            raise TechniquePatternEvidenceError(
                "Existing technique pattern evidence involves different domains."
            )
        if evidence.technique_type != technique_type.value:
            raise TechniquePatternEvidenceError(
                "Existing technique pattern evidence has a different type."
            )
    else:
        evidence = CharacterTechniquePatternEvidence(
            character_id=character.id,
            pattern_key=normalized_pattern,
            domain_keys=normalized_domain_field,
            technique_type=technique_type.value,
            depth=0.0,
            evidence_count=0,
        )
        db.add(evidence)

    world_minute = get_world_time(db, campaign_id).total_minutes()
    cutoff = world_minute - TECHNIQUE_PATTERN_EVIDENCE_WINDOW_MINUTES
    repetition_count = (
        db.query(TechniquePatternEvidenceRecord)
        .filter(
            TechniquePatternEvidenceRecord.character_id == character.id,
            TechniquePatternEvidenceRecord.pattern_key == normalized_pattern,
            TechniquePatternEvidenceRecord.source == source.value,
            TechniquePatternEvidenceRecord.evidence_key == normalized_evidence,
            TechniquePatternEvidenceRecord.world_minute >= cutoff,
        )
        .count()
    )
    multiplier = repetition_multiplier(repetition_count) * _OUTCOME_MULTIPLIER[outcome]
    awarded_amount = base_amount * multiplier

    evidence.depth += awarded_amount
    evidence.evidence_count += 1

    record = TechniquePatternEvidenceRecord(
        campaign_id=campaign_id,
        character_id=character.id,
        pattern_key=normalized_pattern,
        source=source.value,
        outcome=outcome.value,
        evidence_key=normalized_evidence,
        context_key=normalized_context,
        base_amount=base_amount,
        awarded_amount=awarded_amount,
        repetition_count=repetition_count,
        world_minute=world_minute,
    )
    db.add(record)
    db.flush()
    return TechniquePatternEvidenceAward(evidence, record, multiplier)


def technique_pattern_maturity(
    db: Session,
    character_id: str,
    pattern_key: str,
) -> TechniquePatternMaturity:
    normalized_pattern = _normalize_pattern_key(pattern_key)
    evidence = (
        db.query(CharacterTechniquePatternEvidence)
        .filter(
            CharacterTechniquePatternEvidence.character_id == character_id,
            CharacterTechniquePatternEvidence.pattern_key == normalized_pattern,
        )
        .first()
    )
    if evidence is None:
        return TechniquePatternMaturity(
            pattern_key=normalized_pattern,
            domain_keys=(),
            technique_type="",
            depth=0.0,
            evidence_count=0,
            mature=False,
        )
    domain_keys = tuple(evidence.domain_keys.split(","))
    mature = (
        evidence.depth >= TECHNIQUE_RECOGNITION_DEPTH_THRESHOLD
        and evidence.evidence_count >= TECHNIQUE_RECOGNITION_MIN_EVIDENCE_COUNT
    )
    return TechniquePatternMaturity(
        pattern_key=normalized_pattern,
        domain_keys=domain_keys,
        technique_type=evidence.technique_type,
        depth=evidence.depth,
        evidence_count=evidence.evidence_count,
        mature=mature,
    )
