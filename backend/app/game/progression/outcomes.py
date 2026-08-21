import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService, LLMServiceError
from app.core.enums import (
    AttributeEvidenceSource,
    CharacterAttributeKey,
    CharacterResourceKey,
    CharacterXPSource,
    DomainEvidenceSource,
    ProfessionActivityOutcome,
    ProfessionXPSource,
    ResourceGrowthSource,
    TechniqueType,
)
from app.core.logging import get_logger
from app.db.models.character import Character
from app.db.models.character_class import CharacterClassOffer
from app.db.models.progression_outcome import AppliedProgressionOutcome
from app.game.attributes.service import award_attribute_development
from app.game.classes.generator import (
    DynamicClassGenerationError,
    generate_dynamic_class_offers,
)
from app.game.classes.service import make_pending_class_offers_available
from app.game.domains.service import (
    award_domain_evidence,
    award_domain_synergy_evidence,
)
from app.game.professions.activities import award_profession_activity_xp
from app.game.progression.service import award_character_xp
from app.game.resources.service import award_resource_development
from app.game.skills.technique_evidence import award_technique_pattern_evidence
from app.game.skills.technique_mastery import award_technique_mastery
from app.game.time.clock import get_world_time


logger = get_logger("game")
_OUTCOME_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,199}$")


@dataclass(frozen=True)
class CharacterXPGain:
    amount: float
    source: CharacterXPSource


@dataclass(frozen=True)
class ProfessionProgressGain:
    source: ProfessionXPSource
    profession_key: str
    profession_name: str
    activity_key: str
    base_xp: float
    task_complexity_level: int
    outcome: ProfessionActivityOutcome = ProfessionActivityOutcome.SUCCESS
    learning_quality: float = 1.0


@dataclass(frozen=True)
class DomainProgressGain:
    domain_key: str
    source: DomainEvidenceSource
    evidence_key: str
    context_key: str
    amount: float


@dataclass(frozen=True)
class DomainSynergyProgressGain:
    first_domain_key: str
    second_domain_key: str
    source: DomainEvidenceSource
    evidence_key: str
    context_key: str
    amount: float


@dataclass(frozen=True)
class TechniquePatternProgressGain:
    """Evidence toward recognizing a not-yet-existing technique. See
    app.game.skills.technique_evidence — pattern_key identifies the specific
    attempted maneuver, distinct from the domains it draws on."""

    pattern_key: str
    domain_keys: tuple[str, ...]
    technique_type: TechniqueType
    source: DomainEvidenceSource
    outcome: ProfessionActivityOutcome
    evidence_key: str
    context_key: str
    base_amount: float


@dataclass(frozen=True)
class TechniqueMasteryProgressGain:
    """Growth toward a LEARNED technique's mastery tier. See
    app.game.skills.technique_mastery — mastery only ever affects execution
    reliability here, never damage."""

    technique_id: str
    evidence_key: str
    context_key: str
    amount: float


@dataclass(frozen=True)
class AttributeProgressGain:
    attribute_key: CharacterAttributeKey
    source: AttributeEvidenceSource
    evidence_key: str
    context_key: str
    amount: float


@dataclass(frozen=True)
class ResourceProgressGain:
    resource_key: CharacterResourceKey
    source: ResourceGrowthSource
    evidence_key: str
    context_key: str
    amount: float
    contributing_attribute_key: CharacterAttributeKey | None = None


@dataclass(frozen=True)
class ProgressionOutcome:
    """Structured facts emitted by an authoritative mechanical resolver."""

    outcome_key: str
    character_xp: CharacterXPGain | None = None
    professions: tuple[ProfessionProgressGain, ...] = ()
    domains: tuple[DomainProgressGain, ...] = ()
    synergies: tuple[DomainSynergyProgressGain, ...] = ()
    technique_patterns: tuple[TechniquePatternProgressGain, ...] = ()
    technique_masteries: tuple[TechniqueMasteryProgressGain, ...] = ()
    attributes: tuple[AttributeProgressGain, ...] = ()
    resources: tuple[ResourceProgressGain, ...] = ()
    safe_to_notify: bool = False


@dataclass(frozen=True)
class ProgressionResolution:
    applied: bool
    class_offers_created: tuple[CharacterClassOffer, ...] = ()
    class_offers_revealed: tuple[CharacterClassOffer, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)


def resolve_progression_outcome(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    character: Character,
    outcome: ProgressionOutcome,
) -> ProgressionResolution:
    """Apply one trusted mechanical outcome exactly once, then evaluate classes."""
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    normalized_key = outcome.outcome_key.strip().lower()
    if not _OUTCOME_KEY_PATTERN.fullmatch(normalized_key):
        raise ValueError("Invalid progression outcome key.")

    existing = (
        db.query(AppliedProgressionOutcome)
        .filter(
            AppliedProgressionOutcome.campaign_id == campaign_id,
            AppliedProgressionOutcome.character_id == character.id,
            AppliedProgressionOutcome.outcome_key == normalized_key,
        )
        .one_or_none()
    )
    if existing is not None:
        return _evaluate_classes(
            db,
            llm_service,
            campaign_id,
            character,
            safe_to_notify=outcome.safe_to_notify,
            applied=False,
        )

    if outcome.character_xp is not None:
        award_character_xp(
            db,
            campaign_id,
            character,
            outcome.character_xp.amount,
            source=outcome.character_xp.source,
            experience_key=f"progression:{normalized_key}",
        )
    for gain in outcome.professions:
        award_profession_activity_xp(
            db,
            campaign_id,
            character,
            source=gain.source,
            profession_key=gain.profession_key,
            profession_name=gain.profession_name,
            activity_key=gain.activity_key,
            base_xp=gain.base_xp,
            task_complexity_level=gain.task_complexity_level,
            outcome=gain.outcome,
            learning_quality=gain.learning_quality,
        )
    for gain in outcome.domains:
        award_domain_evidence(
            db,
            campaign_id,
            character,
            domain_key=gain.domain_key,
            source=gain.source,
            evidence_key=gain.evidence_key,
            context_key=gain.context_key,
            amount=gain.amount,
        )
    for gain in outcome.synergies:
        award_domain_synergy_evidence(
            db,
            campaign_id,
            character,
            first_domain_key=gain.first_domain_key,
            second_domain_key=gain.second_domain_key,
            source=gain.source,
            evidence_key=gain.evidence_key,
            context_key=gain.context_key,
            amount=gain.amount,
        )
    for gain in outcome.technique_patterns:
        award_technique_pattern_evidence(
            db,
            campaign_id,
            character,
            pattern_key=gain.pattern_key,
            domain_keys=gain.domain_keys,
            technique_type=gain.technique_type,
            source=gain.source,
            outcome=gain.outcome,
            evidence_key=gain.evidence_key,
            context_key=gain.context_key,
            base_amount=gain.base_amount,
        )
    for gain in outcome.technique_masteries:
        award_technique_mastery(
            db,
            character.id,
            gain.technique_id,
            amount=gain.amount,
        )
    for gain in outcome.attributes:
        award_attribute_development(
            db,
            campaign_id,
            character,
            attribute_key=gain.attribute_key,
            source=gain.source,
            evidence_key=gain.evidence_key,
            context_key=gain.context_key,
            amount=gain.amount,
        )
    for gain in outcome.resources:
        award_resource_development(
            db,
            campaign_id,
            character,
            resource_key=gain.resource_key,
            source=gain.source,
            evidence_key=gain.evidence_key,
            context_key=gain.context_key,
            amount=gain.amount,
            contributing_attribute_key=gain.contributing_attribute_key,
        )

    db.add(
        AppliedProgressionOutcome(
            campaign_id=campaign_id,
            character_id=character.id,
            outcome_key=normalized_key,
            applied_world_minute=get_world_time(db, campaign_id).total_minutes(),
        )
    )
    db.flush()
    return _evaluate_classes(
        db,
        llm_service,
        campaign_id,
        character,
        safe_to_notify=outcome.safe_to_notify,
        applied=True,
    )


def _evaluate_classes(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    character: Character,
    *,
    safe_to_notify: bool,
    applied: bool,
) -> ProgressionResolution:
    warnings: list[str] = []
    created: list[CharacterClassOffer] = []
    try:
        created = generate_dynamic_class_offers(
            db,
            llm_service,
            campaign_id,
            character,
        )
    except (LLMServiceError, DynamicClassGenerationError, ValueError) as exc:
        logger.warning("Dynamic class evaluation deferred: %s", exc)
        warnings.append("Dynamic class evaluation was deferred.")

    revealed = make_pending_class_offers_available(
        db,
        campaign_id,
        character,
        safe_to_notify=safe_to_notify,
    )
    db.flush()
    return ProgressionResolution(
        applied=applied,
        class_offers_created=tuple(created),
        class_offers_revealed=tuple(
            offer for offer in revealed if offer.status == "AVAILABLE"
        ),
        warnings=tuple(warnings),
    )
