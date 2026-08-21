import random
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterResourceKey,
    DomainEvidenceSource,
    EventType,
    ProfessionActivityOutcome,
    TechniqueType,
)
from app.db.models.character import Character
from app.db.models.domain import DomainDefinition
from app.db.models.technique_evidence import TechniqueExperimentRecord
from app.game.domains.service import DOMAIN_CHECK_DEFAULT_DC, resolve_domain_check
from app.game.progression.outcomes import ProgressionOutcome, TechniquePatternProgressGain
from app.game.time.clock import get_world_time
from app.services.event_log import log_event

# Phase 11I — Player-Created / Emergent Techniques. A freeform attempt is
# resolved here purely from authoritative facts (accumulated domain depth,
# available resources) — the LLM only supplied what the player described.
# The result feeds technique-pattern evidence (11C); it never creates a
# Technique by itself (that's recognize_technique_from_pattern, 11C/11H,
# invoked later once a pattern matures — 11J's job to decide when/how).

TECHNIQUE_EXPERIMENT_MINUTES = 5
TECHNIQUE_EXPERIMENT_RESOURCE_COST = 3.0
TECHNIQUE_EXPERIMENT_BASE_EVIDENCE = 1.0
_ACTION_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,179}$")


class TechniqueExperimentError(ValueError):
    pass


@dataclass(frozen=True)
class TechniqueExperimentResolution:
    mechanical_summary: str
    progression_outcome: ProgressionOutcome
    replayed: bool


def _slugify_pattern_key(text: str) -> str:
    """Turn whatever the LLM proposed (or, failing that, the player's own
    raw words) into a valid, stable pattern_key. Deliberately simple —
    exact rephrasings of the "same" attempt may still slugify differently,
    fragmenting evidence across keys; per the spec ("design for future
    similarity detection without overengineering it now") that refinement
    is left for later, not solved here."""
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "-", without_accents).strip("-")
    if not slug:
        slug = "tentativa"
    if not slug[0].isalnum():
        slug = f"p-{slug}"
    return slug[:180]


def _known_domain_keys(db: Session, raw_domains: str | None) -> tuple[str, ...]:
    """Only domains the backend actually recognizes — an LLM-proposed key
    that doesn't exist is silently dropped, never trusted at face value.
    raw_domains is the Intent's own "+"-joined string (e.g. "WIND+SWORD")."""
    if not raw_domains:
        return ()
    candidates = tuple(
        sorted({part.strip().upper() for part in raw_domains.split("+") if part.strip()})
    )
    if not candidates:
        return ()
    known = {
        row.key
        for row in db.query(DomainDefinition).filter(DomainDefinition.key.in_(candidates)).all()
    }
    return tuple(key for key in candidates if key in known)


def _parse_technique_type(raw_technique_type: str | None) -> TechniqueType:
    if raw_technique_type is None:
        return TechniqueType.PHYSICAL
    try:
        return TechniqueType(raw_technique_type.strip().upper())
    except ValueError:
        return TechniqueType.PHYSICAL


def resolve_technique_experiment(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    raw_text: str,
    proposed_pattern_key: str | None,
    proposed_domains: str | None,
    proposed_technique_type: str | None,
    action_key: str,
    rng: random.Random | None = None,
) -> TechniqueExperimentResolution:
    if character.campaign_id != campaign_id:
        raise TechniqueExperimentError("Character does not belong to campaign.")
    normalized_action_key = action_key.strip().lower()
    if not _ACTION_KEY_PATTERN.fullmatch(normalized_action_key):
        raise TechniqueExperimentError("Invalid experiment action key.")

    existing = (
        db.query(TechniqueExperimentRecord)
        .filter(
            TechniqueExperimentRecord.campaign_id == campaign_id,
            TechniqueExperimentRecord.character_id == character.id,
            TechniqueExperimentRecord.action_key == normalized_action_key,
        )
        .one_or_none()
    )
    if existing is not None:
        return TechniqueExperimentResolution(
            mechanical_summary=_summary_for(character, existing),
            progression_outcome=_outcome_for(character, existing),
            replayed=True,
        )

    domain_keys = _known_domain_keys(db, proposed_domains)
    technique_type = _parse_technique_type(proposed_technique_type)
    if not domain_keys:
        return TechniqueExperimentResolution(
            mechanical_summary=(
                f"{character.name} tenta algo que não corresponde a nenhuma capacidade "
                "reconhecível. Nada acontece."
            ),
            progression_outcome=ProgressionOutcome(outcome_key=f"experiment-noop:{normalized_action_key}"),
            replayed=False,
        )

    resource_key = (
        CharacterResourceKey.MANA
        if technique_type in (TechniqueType.MAGICAL, TechniqueType.HYBRID)
        else CharacterResourceKey.STAMINA
    )
    resource_field = f"{resource_key.value.lower()}_current"
    available = float(getattr(character, resource_field))
    if available < TECHNIQUE_EXPERIMENT_RESOURCE_COST:
        return TechniqueExperimentResolution(
            mechanical_summary=(
                f"{character.name} tenta, mas não tem {resource_key.value.lower()} "
                "suficiente para a tentativa."
            ),
            progression_outcome=ProgressionOutcome(outcome_key=f"experiment-noop:{normalized_action_key}"),
            replayed=False,
        )

    pattern_key = _slugify_pattern_key(proposed_pattern_key or raw_text)
    check = resolve_domain_check(
        db, character.id, domain_keys, DOMAIN_CHECK_DEFAULT_DC, rng=rng
    )

    margin = check.roll.total - check.dc
    if not check.success:
        outcome = ProfessionActivityOutcome.FAILURE
    elif check.critical or margin >= 5:
        outcome = ProfessionActivityOutcome.SUCCESS
    else:
        outcome = ProfessionActivityOutcome.PARTIAL

    setattr(character, resource_field, available - TECHNIQUE_EXPERIMENT_RESOURCE_COST)

    record = TechniqueExperimentRecord(
        campaign_id=campaign_id,
        character_id=character.id,
        pattern_key=pattern_key,
        domain_keys=",".join(domain_keys),
        technique_type=technique_type.value,
        action_key=normalized_action_key,
        roll=check.roll.raw,
        modifier=check.roll.modifier,
        total=check.roll.total,
        dc=check.dc,
        success=check.success,
        critical=check.critical,
        outcome=outcome.value,
        resource_key=resource_key.value,
        resource_cost=TECHNIQUE_EXPERIMENT_RESOURCE_COST,
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
            "intent": "EXPERIMENT",
            "pattern_key": pattern_key,
            "domains": list(domain_keys),
            "roll": check.roll.raw,
            "modifier": check.roll.modifier,
            "total": check.roll.total,
            "dc": check.dc,
            "success": check.success,
            "critical": check.critical,
            "outcome": outcome.value,
        },
    )
    db.flush()

    return TechniqueExperimentResolution(
        mechanical_summary=_summary_for(character, record),
        progression_outcome=_outcome_for(character, record),
        replayed=False,
    )


_OUTCOME_LABEL = {
    ProfessionActivityOutcome.SUCCESS.value: "consegue controlar a manifestação",
    ProfessionActivityOutcome.PARTIAL.value: "consegue um efeito instável e parcial",
    ProfessionActivityOutcome.FAILURE.value: "não consegue manifestar nada útil",
}


def _summary_for(character: Character, record: TechniqueExperimentRecord) -> str:
    label = _OUTCOME_LABEL[record.outcome]
    return (
        f"{character.name} experimenta algo novo envolvendo {record.domain_keys.replace(',', ' + ')} "
        f"e {label} (rolou {record.roll}+{record.modifier}={record.total} contra CD {record.dc}). "
        f"Gasta {record.resource_cost} de {record.resource_key.lower()}."
    )


def _outcome_for(character: Character, record: TechniqueExperimentRecord) -> ProgressionOutcome:
    domain_keys = tuple(record.domain_keys.split(","))
    return ProgressionOutcome(
        outcome_key=f"experiment:{record.action_key}",
        technique_patterns=(
            TechniquePatternProgressGain(
                pattern_key=record.pattern_key,
                domain_keys=domain_keys,
                technique_type=TechniqueType(record.technique_type),
                source=DomainEvidenceSource.EXPERIMENTATION,
                outcome=ProfessionActivityOutcome(record.outcome),
                # Fixed (not action_key-based): repeating the SAME pattern
                # gets real diminishing returns, matching the anti-farming
                # rule 11C already enforces for every other evidence source.
                evidence_key="freeform-attempt",
                context_key=f"location:{character.location_id or 'unknown'}",
                base_amount=TECHNIQUE_EXPERIMENT_BASE_EVIDENCE,
            ),
        ),
        safe_to_notify=True,
    )
