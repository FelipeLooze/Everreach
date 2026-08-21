import re
from dataclasses import dataclass
from itertools import combinations

from sqlalchemy.orm import Session

from app.core.enums import (
    ActionIntentType,
    DomainEvidenceSource,
    EventType,
    TechniqueLearningState,
    TechniqueOrigin,
    TechniqueType,
)
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
    TechniqueMasteryProgressGain,
)
from app.game.skills.technique_evidence import technique_pattern_maturity
from app.game.skills.technique_mastery import technique_mastery_reliability_bonus
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


TECHNIQUE_USE_DOMAIN_EVIDENCE = 0.5
TECHNIQUE_USE_SYNERGY_EVIDENCE = 0.5
TECHNIQUE_MASTERY_GAIN = 0.5
TECHNIQUE_MASTERY_CRITICAL_MULTIPLIER = 1.5
TECHNIQUE_MASTERY_FAILURE_MULTIPLIER = 0.25
MAX_TECHNIQUE_DOMAINS = 4
TECHNIQUE_ACTION_MINUTES = 5
_ACTION_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,179}$")


class TechniqueUseError(ValueError):
    pass


class TechniqueLearningError(ValueError):
    pass


class TechniqueRecognitionError(ValueError):
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
    technique_type: TechniqueType,
    description: str = "",
    domain_keys: tuple[str, ...],
    parent_technique_id: str | None = None,
) -> Technique:
    """Create immutable technique mechanics from catalog-backed domains.

    parent_technique_id is pure provenance (Phase 11H) — an existing
    technique this one emerged as a variant of practicing (e.g. Focused
    Wind Push refining Wind Push). It must share at least one domain with
    the parent, so lineage reflects a real continuity rather than an
    arbitrary label; it never gates learning, using, or recognizing either
    technique.
    """
    normalized_skill = " ".join(skill_name.split())
    normalized_name = " ".join(name.split())
    normalized_domains = tuple(
        sorted({domain_key.strip().upper() for domain_key in domain_keys})
    )
    if not normalized_skill:
        raise ValueError("Technique skill is required.")
    if not normalized_name:
        raise ValueError("Technique name is required.")
    if not isinstance(technique_type, TechniqueType):
        raise ValueError("Invalid technique type.")
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
    parent_technique: Technique | None = None
    if parent_technique_id is not None:
        parent_technique = db.get(Technique, parent_technique_id)
        if parent_technique is None:
            raise ValueError("Parent technique does not exist.")
        parent_domains = {row.domain_key for row in parent_technique.domains}
        if parent_domains.isdisjoint(normalized_domains):
            raise ValueError(
                "A technique can only be a variant of a parent it shares a domain with."
            )

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
        if existing.technique_type != technique_type.value:
            raise ValueError("Existing technique has a different type.")
        if existing.parent_technique_id != parent_technique_id:
            raise ValueError("Existing technique has a different parent technique.")
        return existing

    technique = Technique(
        skill_id=skill.id,
        name=normalized_name,
        technique_type=technique_type.value,
        description=" ".join(description.split()),
        parent_technique_id=parent_technique_id,
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


def technique_lineage(db: Session, technique_id: str) -> list[Technique]:
    """The technique's "family" (Phase 11H): the root ancestor reached by
    following parent_technique_id up, plus every technique (at any depth)
    descending from that root — an emerged tree, not a predetermined one,
    since every edge only exists because create_technique validated it at
    the moment a variant was actually recognized."""
    technique = db.get(Technique, technique_id)
    if technique is None:
        raise ValueError("Unknown technique.")
    root = technique
    while root.parent_technique_id is not None:
        root = db.get(Technique, root.parent_technique_id)

    family = [root]
    frontier = [root.id]
    while frontier:
        children = (
            db.query(Technique)
            .filter(Technique.parent_technique_id.in_(frontier))
            .order_by(Technique.name, Technique.id)
            .all()
        )
        family.extend(children)
        frontier = [child.id for child in children]
    return family


def find_similar_techniques(
    db: Session,
    *,
    domain_keys: tuple[str, ...],
    technique_type: TechniqueType,
    exclude_technique_id: str | None = None,
) -> list[Technique]:
    """Other existing techniques sharing the exact same domain set and type
    — a deliberately conservative first cut at similarity (Phase 11H:
    "design for future similarity detection without overengineering it
    now"). Advisory only: nothing calls this to merge or block technique
    creation; it exists for a future caller (11J) to show what already
    exists for inspiration/consistency without forcing a merge — different
    characters may still independently end up with distinct techniques."""
    normalized_domains = ",".join(
        sorted({domain_key.strip().upper() for domain_key in domain_keys})
    )
    candidates = (
        db.query(Technique)
        .filter(Technique.technique_type == technique_type.value)
        .order_by(Technique.name, Technique.id)
        .all()
    )
    return [
        candidate
        for candidate in candidates
        if candidate.id != exclude_technique_id
        and ",".join(sorted(row.domain_key for row in candidate.domains)) == normalized_domains
    ]


def _find_character_technique(
    db: Session,
    character: Character,
    technique: Technique,
) -> CharacterTechnique | None:
    return (
        db.query(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character.id,
            CharacterTechnique.technique_id == technique.id,
        )
        .one_or_none()
    )


def _validate_learning_call(
    character: Character,
    campaign_id: str,
    origin: TechniqueOrigin,
) -> None:
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    if not isinstance(origin, TechniqueOrigin):
        raise ValueError("Invalid technique origin.")


def mark_technique_aware(
    db: Session,
    campaign_id: str,
    character: Character,
    technique: Technique,
    *,
    origin: TechniqueOrigin,
) -> CharacterTechnique:
    """The character now knows this technique exists — not that they can
    perform it. A no-op if they are already at least this far along."""
    _validate_learning_call(character, campaign_id, origin)
    existing = _find_character_technique(db, character, technique)
    if existing is not None:
        return existing
    link = CharacterTechnique(
        character_id=character.id,
        technique_id=technique.id,
        learning_state=TechniqueLearningState.AWARE.value,
        origin=origin.value,
        world_minute=get_world_time(db, campaign_id).total_minutes(),
    )
    db.add(link)
    log_event(
        db,
        campaign_id,
        EventType.TECHNIQUE_AWARENESS_GAINED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "technique_id": technique.id,
            "technique_name": technique.name,
            "origin": origin.value,
        },
    )
    db.flush()
    return link


def begin_learning_technique(
    db: Session,
    campaign_id: str,
    character: Character,
    technique: Technique,
    *,
    origin: TechniqueOrigin,
) -> CharacterTechnique:
    """Move from AWARE to actively practicing. Requires prior awareness — a
    character cannot start learning something they don't know exists."""
    _validate_learning_call(character, campaign_id, origin)
    existing = _find_character_technique(db, character, technique)
    if existing is None:
        raise TechniqueLearningError(
            "Character must be aware of a technique before starting to learn it."
        )
    if existing.learning_state in (
        TechniqueLearningState.LEARNING.value,
        TechniqueLearningState.LEARNED.value,
    ):
        return existing
    existing.learning_state = TechniqueLearningState.LEARNING.value
    existing.origin = origin.value
    existing.world_minute = get_world_time(db, campaign_id).total_minutes()
    log_event(
        db,
        campaign_id,
        EventType.TECHNIQUE_LEARNING_STARTED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "technique_id": technique.id,
            "technique_name": technique.name,
            "origin": origin.value,
        },
    )
    db.flush()
    return existing


def grant_technique(
    db: Session,
    campaign_id: str,
    character: Character,
    technique: Technique,
    *,
    origin: TechniqueOrigin,
) -> CharacterTechnique:
    """Mark a technique as fully learned — the character can now attempt it.
    Works from any prior state (including no prior row at all): a technique
    recognized from mature evidence, or taught hands-on, does not have to
    pass through AWARE/LEARNING as separate calls first."""
    _validate_learning_call(character, campaign_id, origin)
    existing = _find_character_technique(db, character, technique)
    if existing is not None and existing.learning_state == TechniqueLearningState.LEARNED.value:
        return existing
    world_minute = get_world_time(db, campaign_id).total_minutes()
    if existing is None:
        existing = CharacterTechnique(
            character_id=character.id,
            technique_id=technique.id,
        )
        db.add(existing)
    existing.learning_state = TechniqueLearningState.LEARNED.value
    existing.origin = origin.value
    existing.world_minute = world_minute
    log_event(
        db,
        campaign_id,
        EventType.TECHNIQUE_LEARNED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "technique_id": technique.id,
            "technique_name": technique.name,
            "origin": origin.value,
        },
    )
    db.flush()
    return existing


def recognize_technique_from_pattern(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    pattern_key: str,
    name: str,
    description: str = "",
    parent_technique_id: str | None = None,
) -> Technique:
    """Turn a mature, reproducible pattern into a real, usable Technique.

    This is the mechanical half of recognition: it verifies the pattern has
    actually crossed the reproducibility threshold
    (technique_evidence.technique_pattern_maturity) and, if so, persists the
    Technique and grants it to the character as LEARNED with
    origin=SELF_DISCOVERED — the character earned this through their own
    practice, not a gift.

    Naming is deliberately NOT this function's job: the backend never invents
    a technique's identity on its own (Phase 11J — an LLM proposes name and
    description from the same authoritative evidence this function checks;
    the backend only validates and persists). `name`/`description` are
    supplied by the caller, and so is `parent_technique_id` (Phase 11H) when
    this pattern is recognized as a variant of something the character
    already knows — never inferred automatically.
    """
    maturity = technique_pattern_maturity(db, character.id, pattern_key)
    if not maturity.reproducible:
        raise TechniqueRecognitionError(
            "This pattern is not yet reproducible enough to be recognized as a technique."
        )
    if not maturity.has_required_synergy:
        raise TechniqueRecognitionError(
            "Possessing multiple domains is not enough — this pattern combines domains "
            "that have not been genuinely integrated yet (no real Domain Synergy between "
            "them). Practice them together, not just separately, before this can be "
            "recognized as a hybrid technique."
        )
    skill_name = " + ".join(key.title() for key in maturity.domain_keys)
    technique = create_technique(
        db,
        skill_name=skill_name,
        name=name,
        technique_type=TechniqueType(maturity.technique_type),
        description=description,
        domain_keys=maturity.domain_keys,
        parent_technique_id=parent_technique_id,
    )
    log_event(
        db,
        campaign_id,
        EventType.TECHNIQUE_RECOGNIZED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "technique_id": technique.id,
            "technique_name": technique.name,
            "pattern_key": maturity.pattern_key,
            "domain_keys": list(maturity.domain_keys),
        },
    )
    grant_technique(db, campaign_id, character, technique, origin=TechniqueOrigin.SELF_DISCOVERED)
    return technique


def list_character_techniques(
    db: Session,
    character_id: str,
) -> list[Technique]:
    """Techniques the character can actually attempt. Being merely AWARE or
    LEARNING a technique does not make it usable — see resolve_technique_use."""
    return (
        db.query(Technique)
        .join(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character_id,
            CharacterTechnique.learning_state == TechniqueLearningState.LEARNED.value,
        )
        .order_by(Technique.name, Technique.id)
        .all()
    )


def resolve_named_technique(
    db: Session,
    character_id: str,
    name: str | None,
) -> Technique | None:
    """Which of the character's LEARNED techniques the player meant by name
    (Phase 11K) — a case-insensitive substring match, same shape as how
    combat_bridge resolves a named weapon/opponent. Returns None on no match
    or an ambiguous one; the caller decides how to report that, since a
    "no such technique" message differs from "which one do you mean"."""
    if not name:
        return None
    needle = name.casefold()
    candidates = [
        technique
        for technique in list_character_techniques(db, character_id)
        if needle in technique.name.casefold()
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


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
    ownership = _find_character_technique(db, character, technique)
    if ownership is None:
        raise TechniqueUseError("Character does not know this technique.")
    if ownership.learning_state != TechniqueLearningState.LEARNED.value:
        raise TechniqueUseError(
            "Character is aware of this technique but has not learned to perform it yet."
        )
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
            progression_outcome=technique_progression_outcome(
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
        bonus_modifier=technique_mastery_reliability_bonus(ownership.mastery),
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
        progression_outcome=technique_progression_outcome(
            character,
            technique,
            domain_keys,
            record,
        ),
        replayed=False,
    )


def technique_progression_outcome(
    character: Character,
    technique: Technique,
    domain_keys: tuple[str, ...],
    record: TechniqueUseRecord,
) -> ProgressionOutcome:
    domains: tuple[DomainProgressGain, ...] = ()
    synergies: tuple[DomainSynergyProgressGain, ...] = ()
    evidence_key = f"technique:{technique.id}"
    context_key = f"location:{character.location_id or 'unknown'}"
    if record.success:
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
        mastery_amount = TECHNIQUE_MASTERY_GAIN * (
            TECHNIQUE_MASTERY_CRITICAL_MULTIPLIER if record.critical else 1.0
        )
    else:
        # A failed attempt is still real practice — worth little, but not
        # nothing (same principle 11C applies to pattern evidence).
        mastery_amount = TECHNIQUE_MASTERY_GAIN * TECHNIQUE_MASTERY_FAILURE_MULTIPLIER
    technique_masteries = (
        TechniqueMasteryProgressGain(
            technique_id=technique.id,
            evidence_key=evidence_key,
            context_key=context_key,
            amount=mastery_amount,
        ),
    )
    return ProgressionOutcome(
        outcome_key=f"technique:{record.action_key}",
        domains=domains,
        synergies=synergies,
        technique_masteries=technique_masteries,
        safe_to_notify=True,
    )
