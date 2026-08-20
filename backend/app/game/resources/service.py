from dataclasses import dataclass
from math import isfinite

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    CharacterResourceKey,
    EventType,
    ResourceGrowthSource,
)
from app.db.models.character import Character
from app.db.models.resource import (
    CharacterResourceGrowth,
    ResourceGrowthEvidenceRecord,
)
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


RESOURCE_REPETITION_WINDOW_MINUTES = 24 * 60

_ALLOWED_SOURCES: dict[CharacterResourceKey, set[ResourceGrowthSource]] = {
    CharacterResourceKey.HP: {
        ResourceGrowthSource.ATTRIBUTE_DEVELOPMENT,
        ResourceGrowthSource.PHYSICAL_CONDITIONING,
        ResourceGrowthSource.RECOVERY_CHALLENGE,
        ResourceGrowthSource.REAL_CHALLENGE,
        ResourceGrowthSource.TECHNIQUE_MASTERY,
        ResourceGrowthSource.CLASS_PATH,
    },
    CharacterResourceKey.MANA: {
        ResourceGrowthSource.MAGICAL_PRACTICE,
        ResourceGrowthSource.TECHNIQUE_MASTERY,
        ResourceGrowthSource.REAL_CHALLENGE,
        ResourceGrowthSource.CLASS_PATH,
    },
    CharacterResourceKey.STAMINA: {
        ResourceGrowthSource.ATTRIBUTE_DEVELOPMENT,
        ResourceGrowthSource.PHYSICAL_CONDITIONING,
        ResourceGrowthSource.RESOURCE_EXERTION,
        ResourceGrowthSource.RECOVERY_CHALLENGE,
        ResourceGrowthSource.REAL_CHALLENGE,
        ResourceGrowthSource.TECHNIQUE_MASTERY,
        ResourceGrowthSource.CLASS_PATH,
    },
}

_ATTRIBUTE_RESOURCE_LINKS = {
    CharacterAttributeKey.VITALITY: CharacterResourceKey.HP,
    CharacterAttributeKey.ENDURANCE: CharacterResourceKey.STAMINA,
}


@dataclass(frozen=True)
class ResourceDevelopmentAward:
    growth: CharacterResourceGrowth
    record: ResourceGrowthEvidenceRecord
    repetition_multiplier: float
    increases: int


def resource_development_to_next_max(
    character: Character,
    resource_key: CharacterResourceKey,
) -> float:
    current_max = _maximum(character, resource_key)
    baseline = {
        CharacterResourceKey.HP: 20.0,
        CharacterResourceKey.MANA: 10.0,
        CharacterResourceKey.STAMINA: 20.0,
    }[resource_key]
    base_requirement = {
        CharacterResourceKey.HP: 10.0,
        CharacterResourceKey.MANA: 12.5,
        CharacterResourceKey.STAMINA: 10.0,
    }[resource_key]
    return base_requirement + max(0.0, current_max - baseline) * 2.5


def get_resource_growth(
    db: Session,
    character_id: str,
    resource_key: CharacterResourceKey,
) -> CharacterResourceGrowth | None:
    return (
        db.query(CharacterResourceGrowth)
        .filter(
            CharacterResourceGrowth.character_id == character_id,
            CharacterResourceGrowth.resource_key == resource_key.value,
        )
        .one_or_none()
    )


def award_resource_development(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    resource_key: CharacterResourceKey,
    source: ResourceGrowthSource,
    evidence_key: str,
    context_key: str,
    amount: float,
    contributing_attribute_key: CharacterAttributeKey | None = None,
) -> ResourceDevelopmentAward:
    _validate_award(
        character,
        campaign_id,
        resource_key,
        source,
        amount,
        contributing_attribute_key,
    )
    normalized_evidence = evidence_key.strip().lower()
    normalized_context = context_key.strip().lower()
    if not normalized_evidence:
        raise ValueError("Resource growth evidence key is required.")
    if not normalized_context:
        raise ValueError("Resource growth context is required.")

    world_minute = get_world_time(db, campaign_id).total_minutes()
    cutoff = world_minute - RESOURCE_REPETITION_WINDOW_MINUTES
    repetition_count = (
        db.query(ResourceGrowthEvidenceRecord)
        .filter(
            ResourceGrowthEvidenceRecord.character_id == character.id,
            ResourceGrowthEvidenceRecord.resource_key == resource_key.value,
            ResourceGrowthEvidenceRecord.source == source.value,
            ResourceGrowthEvidenceRecord.evidence_key == normalized_evidence,
            ResourceGrowthEvidenceRecord.world_minute >= cutoff,
        )
        .count()
    )
    repetition_multiplier = 1.0 / (repetition_count + 1)
    awarded_amount = amount * repetition_multiplier

    growth = get_resource_growth(db, character.id, resource_key)
    if growth is None:
        growth = CharacterResourceGrowth(
            character_id=character.id,
            resource_key=resource_key.value,
            development=0.0,
        )
        db.add(growth)
    growth.development += awarded_amount

    record = ResourceGrowthEvidenceRecord(
        campaign_id=campaign_id,
        character_id=character.id,
        resource_key=resource_key.value,
        source=source.value,
        contributing_attribute_key=(
            contributing_attribute_key.value
            if contributing_attribute_key is not None
            else None
        ),
        evidence_key=normalized_evidence,
        context_key=normalized_context,
        base_amount=amount,
        awarded_amount=awarded_amount,
        repetition_count=repetition_count,
        world_minute=world_minute,
    )
    db.add(record)

    increases = 0
    while growth.development >= resource_development_to_next_max(
        character, resource_key
    ):
        required = resource_development_to_next_max(character, resource_key)
        growth.development -= required
        previous_max = _maximum(character, resource_key)
        was_full = _current(character, resource_key) >= previous_max
        _set_maximum(character, resource_key, previous_max + 1.0)
        if was_full:
            _set_current(character, resource_key, previous_max + 1.0)
        increases += 1
        log_event(
            db,
            campaign_id,
            EventType.PLAYER_RESOURCE_MAX_INCREASED,
            actor_type="character",
            actor_id=character.id,
            payload={
                "resource_key": resource_key.value,
                "previous_max": previous_max,
                "new_max": _maximum(character, resource_key),
                "source": source.value,
            },
        )
    db.flush()
    return ResourceDevelopmentAward(
        growth=growth,
        record=record,
        repetition_multiplier=repetition_multiplier,
        increases=increases,
    )


def apply_attribute_resource_growth(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    attribute_key: CharacterAttributeKey,
    attribute_value: int,
) -> ResourceDevelopmentAward:
    resource_key = _ATTRIBUTE_RESOURCE_LINKS.get(attribute_key)
    if resource_key is None:
        raise ValueError("Attribute has no direct resource growth relationship.")
    return award_resource_development(
        db,
        campaign_id,
        character,
        resource_key=resource_key,
        source=ResourceGrowthSource.ATTRIBUTE_DEVELOPMENT,
        contributing_attribute_key=attribute_key,
        evidence_key=f"attribute:{attribute_key.value}:{attribute_value}",
        context_key="attribute-development",
        amount=resource_development_to_next_max(character, resource_key),
    )


def _validate_award(
    character: Character,
    campaign_id: str,
    resource_key: CharacterResourceKey,
    source: ResourceGrowthSource,
    amount: float,
    contributing_attribute_key: CharacterAttributeKey | None,
) -> None:
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    if not isinstance(resource_key, CharacterResourceKey):
        raise ValueError("Invalid character resource key.")
    if not isinstance(source, ResourceGrowthSource):
        raise ValueError("Invalid resource growth source.")
    if source not in _ALLOWED_SOURCES[resource_key]:
        raise ValueError("Growth source is not relevant to this resource.")
    if not isfinite(amount) or amount <= 0:
        raise ValueError("Resource development amount must be finite and positive.")
    if source == ResourceGrowthSource.ATTRIBUTE_DEVELOPMENT:
        expected = {
            CharacterResourceKey.HP: CharacterAttributeKey.VITALITY,
            CharacterResourceKey.STAMINA: CharacterAttributeKey.ENDURANCE,
        }.get(resource_key)
        if contributing_attribute_key != expected:
            raise ValueError("Attribute is not relevant to this resource.")
    elif contributing_attribute_key is not None:
        raise ValueError(
            "Contributing attribute is only valid for attribute development."
        )


def _maximum(character: Character, resource_key: CharacterResourceKey) -> float:
    return float(getattr(character, f"{resource_key.value.lower()}_max"))


def _current(character: Character, resource_key: CharacterResourceKey) -> float:
    return float(getattr(character, f"{resource_key.value.lower()}_current"))


def _set_maximum(
    character: Character,
    resource_key: CharacterResourceKey,
    value: float,
) -> None:
    setattr(character, f"{resource_key.value.lower()}_max", value)


def _set_current(
    character: Character,
    resource_key: CharacterResourceKey,
    value: float,
) -> None:
    setattr(character, f"{resource_key.value.lower()}_current", value)
