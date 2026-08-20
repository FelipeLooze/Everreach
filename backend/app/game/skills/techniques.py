import re
from dataclasses import dataclass
from itertools import combinations

from sqlalchemy.orm import Session

from app.core.enums import ActionIntentType, DomainEvidenceSource, EventType
from app.db.models.character import Character
from app.db.models.domain import DomainDefinition
from app.db.models.skill import (
    CharacterTechnique,
    Skill,
    Technique,
    TechniqueDomain,
    TechniqueUseRecord,
)
from app.game.combat.service import DEFAULT_DC, resolve_skill_check
from app.game.progression.outcomes import (
    DomainProgressGain,
    DomainSynergyProgressGain,
    ProgressionOutcome,
)
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


TECHNIQUE_USE_DOMAIN_EVIDENCE = 0.5
TECHNIQUE_USE_SYNERGY_EVIDENCE = 0.5
MAX_TECHNIQUE_DOMAINS = 4
TECHNIQUE_ACTION_MINUTES = 5
_ACTION_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,179}$")


class TechniqueUseError(ValueError):
    pass


@dataclass(frozen=True)
class TechniqueUseResolution:
    technique: Technique
    domain_keys: tuple[str, ...]
    record: TechniqueUseRecord
    progression_outcome: ProgressionOutcome
    replayed: bool

    @property
    def intent_type(self) -> ActionIntentType:
        return ActionIntentType.TECHNIQUE

    @property
    def mechanical_summary(self) -> str:
        outcome = "tem sucesso" if self.record.success else "falha"
        critical = " (rolagem crítica)" if self.record.critical else ""
        return (
            f"A técnica {self.technique.name} {outcome}{critical} "
            f"(rolou {self.record.roll}+{self.record.modifier}="
            f"{self.record.total} contra CD {self.record.dc})."
        )


def create_technique(
    db: Session,
    *,
    skill_name: str,
    name: str,
    description: str = "",
    domain_keys: tuple[str, ...],
) -> Technique:
    """Create immutable technique mechanics from catalog-backed domains."""
    normalized_skill = " ".join(skill_name.split())
    normalized_name = " ".join(name.split())
    normalized_domains = tuple(
        sorted({domain_key.strip().upper() for domain_key in domain_keys})
    )
    if not normalized_skill:
        raise ValueError("Technique skill is required.")
    if not normalized_name:
        raise ValueError("Technique name is required.")
    if not 1 <= len(normalized_domains) <= MAX_TECHNIQUE_DOMAINS:
        raise ValueError("Technique must have between one and four domains.")
    known_domains = {
        row.key
        for row in db.query(DomainDefinition)
        .filter(DomainDefinition.key.in_(normalized_domains))
        .all()
    }
    if known_domains != set(normalized_domains):
        raise ValueError("Technique contains an unknown domain.")

    skill = db.query(Skill).filter(Skill.name == normalized_skill).one_or_none()
    if skill is None:
        skill = Skill(name=normalized_skill)
        db.add(skill)
        db.flush()
    existing = (
        db.query(Technique)
        .filter(
            Technique.skill_id == skill.id,
            Technique.name == normalized_name,
        )
        .one_or_none()
    )
    if existing is not None:
        existing_domains = tuple(row.domain_key for row in existing.domains)
        if existing_domains != normalized_domains:
            raise ValueError("Existing technique has different domain mechanics.")
        return existing

    technique = Technique(
        skill_id=skill.id,
        name=normalized_name,
        description=" ".join(description.split()),
    )
    db.add(technique)
    db.flush()
    for domain_key in normalized_domains:
        db.add(
            TechniqueDomain(
                technique_id=technique.id,
                domain_key=domain_key,
            )
        )
    db.flush()
    return technique


def grant_technique(
    db: Session,
    campaign_id: str,
    character: Character,
    technique: Technique,
) -> CharacterTechnique:
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    existing = (
        db.query(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character.id,
            CharacterTechnique.technique_id == technique.id,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    link = CharacterTechnique(
        character_id=character.id,
        technique_id=technique.id,
    )
    db.add(link)
    log_event(
        db,
        campaign_id,
        EventType.NEW_TECHNIQUE_CREATED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "technique_id": technique.id,
            "technique_name": technique.name,
        },
    )
    db.flush()
    return link


def list_character_techniques(
    db: Session,
    character_id: str,
) -> list[Technique]:
    return (
        db.query(Technique)
        .join(CharacterTechnique)
        .filter(CharacterTechnique.character_id == character_id)
        .order_by(Technique.name, Technique.id)
        .all()
    )


def resolve_technique_use(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    technique_id: str,
    action_key: str,
) -> TechniqueUseResolution:
    """Resolve a selected known technique and emit factual progression evidence."""
    if character.campaign_id != campaign_id:
        raise TechniqueUseError("Character does not belong to campaign.")
    normalized_action_key = action_key.strip().lower()
    if not _ACTION_KEY_PATTERN.fullmatch(normalized_action_key):
        raise TechniqueUseError("Invalid technique action key.")

    technique = db.get(Technique, technique_id)
    if technique is None:
        raise TechniqueUseError("Unknown technique.")
    ownership = (
        db.query(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character.id,
            CharacterTechnique.technique_id == technique.id,
        )
        .one_or_none()
    )
    if ownership is None:
        raise TechniqueUseError("Character does not know this technique.")
    domain_keys = tuple(row.domain_key for row in technique.domains)
    if not 1 <= len(domain_keys) <= MAX_TECHNIQUE_DOMAINS:
        raise TechniqueUseError("Technique has invalid domain mechanics.")

    existing = (
        db.query(TechniqueUseRecord)
        .filter(
            TechniqueUseRecord.campaign_id == campaign_id,
            TechniqueUseRecord.character_id == character.id,
            TechniqueUseRecord.action_key == normalized_action_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.technique_id != technique.id:
            raise TechniqueUseError("Action key already belongs to another technique.")
        return TechniqueUseResolution(
            technique=technique,
            domain_keys=domain_keys,
            record=existing,
            progression_outcome=_progression_outcome(
                character,
                technique,
                domain_keys,
                existing,
            ),
            replayed=True,
        )

    skill = db.get(Skill, technique.skill_id)
    if skill is None:
        raise TechniqueUseError("Technique skill does not exist.")
    check = resolve_skill_check(
        db,
        character.id,
        skill.name,
        dc=DEFAULT_DC,
    )
    record = TechniqueUseRecord(
        campaign_id=campaign_id,
        character_id=character.id,
        technique_id=technique.id,
        action_key=normalized_action_key,
        roll=check.roll.raw,
        modifier=check.roll.modifier,
        total=check.roll.total,
        dc=check.dc,
        success=check.success,
        critical=check.critical,
        world_minute=get_world_time(db, campaign_id).total_minutes(),
    )
    db.add(record)
    log_event(
        db,
        campaign_id,
        EventType.ACTION_CHECK_RESULT,
        actor_type="character",
        actor_id=character.id,
        payload={
            "action_key": normalized_action_key,
            "intent": ActionIntentType.TECHNIQUE.value,
            "technique_id": technique.id,
            "technique_name": technique.name,
            "domains": list(domain_keys),
            "skill": skill.name,
            "roll": check.roll.raw,
            "modifier": check.roll.modifier,
            "total": check.roll.total,
            "dc": check.dc,
            "success": check.success,
            "critical": check.critical,
        },
    )
    db.flush()
    return TechniqueUseResolution(
        technique=technique,
        domain_keys=domain_keys,
        record=record,
        progression_outcome=_progression_outcome(
            character,
            technique,
            domain_keys,
            record,
        ),
        replayed=False,
    )


def _progression_outcome(
    character: Character,
    technique: Technique,
    domain_keys: tuple[str, ...],
    record: TechniqueUseRecord,
) -> ProgressionOutcome:
    domains: tuple[DomainProgressGain, ...] = ()
    synergies: tuple[DomainSynergyProgressGain, ...] = ()
    if record.success:
        evidence_key = f"technique:{technique.id}"
        context_key = f"location:{character.location_id or 'unknown'}"
        domains = tuple(
            DomainProgressGain(
                domain_key=domain_key,
                source=DomainEvidenceSource.TECHNIQUE_USED,
                evidence_key=evidence_key,
                context_key=context_key,
                amount=TECHNIQUE_USE_DOMAIN_EVIDENCE,
            )
            for domain_key in domain_keys
        )
        synergies = tuple(
            DomainSynergyProgressGain(
                first_domain_key=first,
                second_domain_key=second,
                source=DomainEvidenceSource.TECHNIQUE_USED,
                evidence_key=evidence_key,
                context_key=context_key,
                amount=TECHNIQUE_USE_SYNERGY_EVIDENCE,
            )
            for first, second in combinations(domain_keys, 2)
        )
    return ProgressionOutcome(
        outcome_key=f"technique:{record.action_key}",
        domains=domains,
        synergies=synergies,
        safe_to_notify=True,
    )
