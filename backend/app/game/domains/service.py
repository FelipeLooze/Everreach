from dataclasses import dataclass
from math import isfinite

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import DomainEvidenceSource
from app.db.models.character import Character
from app.db.models.domain import (
    CharacterDomainEvidence,
    CharacterDomainSynergy,
    DomainDefinition,
    DomainEvidenceRecord,
    DomainSynergyRecord,
)
from app.game.time.clock import get_world_time


DOMAIN_REPETITION_WINDOW_MINUTES = 24 * 60


def repetition_multiplier(repetition_count: int) -> float:
    """Diminishing returns for repeating the same identifiable evidence within
    the repetition window — 1.0 on the first occurrence, halved on the
    second, etc. Shared by any evidence engine that needs anti-farming
    (domains here; technique pattern evidence reuses it too)."""
    return 1.0 / (repetition_count + 1)


@dataclass(frozen=True)
class DomainEvidenceAward:
    evidence: CharacterDomainEvidence
    record: DomainEvidenceRecord
    repetition_multiplier: float


@dataclass(frozen=True)
class DomainSynergyAward:
    synergy: CharacterDomainSynergy
    record: DomainSynergyRecord
    repetition_multiplier: float


@dataclass(frozen=True)
class DomainMaturity:
    domain_key: str
    depth: float
    consistency: int
    diversity: int
    synergy_depth: float
    synergy_count: int


def list_domain_catalog(db: Session) -> list[DomainDefinition]:
    return db.query(DomainDefinition).order_by(DomainDefinition.key).all()


def award_domain_evidence(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    domain_key: str,
    source: DomainEvidenceSource,
    evidence_key: str,
    context_key: str,
    amount: float,
) -> DomainEvidenceAward:
    normalized_domain = _validate_award(
        db,
        campaign_id,
        character,
        domain_key,
        source,
        evidence_key,
        context_key,
        amount,
    )
    normalized_evidence = evidence_key.strip().lower()
    normalized_context = context_key.strip().lower()
    world_minute = get_world_time(db, campaign_id).total_minutes()
    cutoff = world_minute - DOMAIN_REPETITION_WINDOW_MINUTES
    repetition_count = (
        db.query(DomainEvidenceRecord)
        .filter(
            DomainEvidenceRecord.character_id == character.id,
            DomainEvidenceRecord.domain_key == normalized_domain,
            DomainEvidenceRecord.source == source.value,
            DomainEvidenceRecord.evidence_key == normalized_evidence,
            DomainEvidenceRecord.world_minute >= cutoff,
        )
        .count()
    )
    multiplier = repetition_multiplier(repetition_count)
    awarded_amount = amount * multiplier

    evidence = (
        db.query(CharacterDomainEvidence)
        .filter(
            CharacterDomainEvidence.character_id == character.id,
            CharacterDomainEvidence.domain_key == normalized_domain,
        )
        .first()
    )
    if evidence is None:
        evidence = CharacterDomainEvidence(
            character_id=character.id,
            domain_key=normalized_domain,
            depth=0.0,
            evidence_count=0,
        )
        db.add(evidence)
    evidence.depth += awarded_amount
    evidence.evidence_count += 1

    record = DomainEvidenceRecord(
        campaign_id=campaign_id,
        character_id=character.id,
        domain_key=normalized_domain,
        source=source.value,
        evidence_key=normalized_evidence,
        context_key=normalized_context,
        base_amount=amount,
        awarded_amount=awarded_amount,
        repetition_count=repetition_count,
        world_minute=world_minute,
    )
    db.add(record)
    db.flush()
    return DomainEvidenceAward(evidence, record, multiplier)


def award_domain_synergy_evidence(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    first_domain_key: str,
    second_domain_key: str,
    source: DomainEvidenceSource,
    evidence_key: str,
    context_key: str,
    amount: float,
) -> DomainSynergyAward:
    first = _validate_award(
        db,
        campaign_id,
        character,
        first_domain_key,
        source,
        evidence_key,
        context_key,
        amount,
    )
    second = _validate_award(
        db,
        campaign_id,
        character,
        second_domain_key,
        source,
        evidence_key,
        context_key,
        amount,
    )
    if first == second:
        raise ValueError("Domain synergy requires two different domains.")
    first, second = sorted((first, second))

    developed_domains = {
        row.domain_key
        for row in db.query(CharacterDomainEvidence)
        .filter(
            CharacterDomainEvidence.character_id == character.id,
            CharacterDomainEvidence.domain_key.in_([first, second]),
            CharacterDomainEvidence.depth > 0,
        )
        .all()
    }
    if developed_domains != {first, second}:
        raise ValueError(
            "Synergy evidence requires real evidence in both domains."
        )

    normalized_evidence = evidence_key.strip().lower()
    normalized_context = context_key.strip().lower()
    world_minute = get_world_time(db, campaign_id).total_minutes()
    cutoff = world_minute - DOMAIN_REPETITION_WINDOW_MINUTES
    repetition_count = (
        db.query(DomainSynergyRecord)
        .filter(
            DomainSynergyRecord.character_id == character.id,
            DomainSynergyRecord.first_domain_key == first,
            DomainSynergyRecord.second_domain_key == second,
            DomainSynergyRecord.source == source.value,
            DomainSynergyRecord.evidence_key == normalized_evidence,
            DomainSynergyRecord.world_minute >= cutoff,
        )
        .count()
    )
    multiplier = repetition_multiplier(repetition_count)
    awarded_amount = amount * multiplier

    synergy = (
        db.query(CharacterDomainSynergy)
        .filter(
            CharacterDomainSynergy.character_id == character.id,
            CharacterDomainSynergy.first_domain_key == first,
            CharacterDomainSynergy.second_domain_key == second,
        )
        .first()
    )
    if synergy is None:
        synergy = CharacterDomainSynergy(
            character_id=character.id,
            first_domain_key=first,
            second_domain_key=second,
            depth=0.0,
            evidence_count=0,
        )
        db.add(synergy)
    synergy.depth += awarded_amount
    synergy.evidence_count += 1

    record = DomainSynergyRecord(
        campaign_id=campaign_id,
        character_id=character.id,
        first_domain_key=first,
        second_domain_key=second,
        source=source.value,
        evidence_key=normalized_evidence,
        context_key=normalized_context,
        base_amount=amount,
        awarded_amount=awarded_amount,
        repetition_count=repetition_count,
        world_minute=world_minute,
    )
    db.add(record)
    db.flush()
    return DomainSynergyAward(synergy, record, multiplier)


def domain_maturity(
    db: Session,
    character_id: str,
    domain_key: str,
) -> DomainMaturity:
    normalized_domain = domain_key.strip().upper()
    evidence = (
        db.query(CharacterDomainEvidence)
        .filter(
            CharacterDomainEvidence.character_id == character_id,
            CharacterDomainEvidence.domain_key == normalized_domain,
        )
        .first()
    )
    records = (
        db.query(DomainEvidenceRecord)
        .filter(
            DomainEvidenceRecord.character_id == character_id,
            DomainEvidenceRecord.domain_key == normalized_domain,
        )
        .all()
    )
    synergies = (
        db.query(CharacterDomainSynergy)
        .filter(
            CharacterDomainSynergy.character_id == character_id,
            or_(
                CharacterDomainSynergy.first_domain_key == normalized_domain,
                CharacterDomainSynergy.second_domain_key == normalized_domain,
            ),
        )
        .all()
    )
    return DomainMaturity(
        domain_key=normalized_domain,
        depth=evidence.depth if evidence is not None else 0.0,
        consistency=len({record.evidence_key for record in records}),
        diversity=len(
            {(record.source, record.context_key) for record in records}
        ),
        synergy_depth=sum(synergy.depth for synergy in synergies),
        synergy_count=len(synergies),
    )


def _validate_award(
    db: Session,
    campaign_id: str,
    character: Character,
    domain_key: str,
    source: DomainEvidenceSource,
    evidence_key: str,
    context_key: str,
    amount: float,
) -> str:
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    if not isinstance(source, DomainEvidenceSource):
        raise ValueError("Invalid domain evidence source.")
    if not isfinite(amount) or amount <= 0:
        raise ValueError("Domain evidence amount must be finite and positive.")
    if not evidence_key.strip():
        raise ValueError("Domain evidence key is required.")
    if not context_key.strip():
        raise ValueError("Domain evidence context is required.")
    normalized_domain = domain_key.strip().upper()
    if db.get(DomainDefinition, normalized_domain) is None:
        raise ValueError("Unknown domain cannot receive evidence.")
    return normalized_domain
