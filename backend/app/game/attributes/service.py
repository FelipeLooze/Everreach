from dataclasses import dataclass
from math import isfinite

from sqlalchemy.orm import Session

from app.core.enums import (
    AttributeEvidenceSource,
    CharacterAttributeKey,
    EventType,
)
from app.db.models.attribute import AttributeDefinition, AttributeEvidenceRecord
from app.db.models.character import Character, CharacterAttribute
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


ATTRIBUTE_REPETITION_WINDOW_MINUTES = 24 * 60

ATTRIBUTE_CATALOG: dict[CharacterAttributeKey, tuple[str, str]] = {
    CharacterAttributeKey.STRENGTH: (
        "Força",
        "Capacidade física para levantar, carregar, empurrar e aplicar potência.",
    ),
    CharacterAttributeKey.AGILITY: (
        "Agilidade",
        "Coordenação, precisão motora, equilíbrio e movimentos delicados.",
    ),
    CharacterAttributeKey.VITALITY: (
        "Vitalidade",
        "Robustez, saúde física, recuperação e tolerância corporal.",
    ),
    CharacterAttributeKey.INTELLIGENCE: (
        "Inteligência",
        "Raciocínio, análise, pesquisa e compreensão técnica.",
    ),
    CharacterAttributeKey.WISDOM: (
        "Sabedoria",
        "Percepção, intuição, sensibilidade e leitura do ambiente.",
    ),
    CharacterAttributeKey.ENDURANCE: (
        "Resistência",
        "Capacidade de continuar funcionando sob esforço e adversidade.",
    ),
    CharacterAttributeKey.LUCK: (
        "Sorte",
        "Atributo reservado para futuras resoluções autoritativas de loot.",
    ),
}

_ALLOWED_SOURCES: dict[CharacterAttributeKey, set[AttributeEvidenceSource]] = {
    CharacterAttributeKey.STRENGTH: {
        AttributeEvidenceSource.TRAINING,
        AttributeEvidenceSource.PHYSICAL_EXERTION,
        AttributeEvidenceSource.REAL_CHALLENGE,
    },
    CharacterAttributeKey.AGILITY: {
        AttributeEvidenceSource.TRAINING,
        AttributeEvidenceSource.PERCEPTIVE_EXPERIENCE,
        AttributeEvidenceSource.REAL_CHALLENGE,
    },
    CharacterAttributeKey.VITALITY: {
        AttributeEvidenceSource.PHYSICAL_EXERTION,
        AttributeEvidenceSource.RECOVERY_CHALLENGE,
        AttributeEvidenceSource.REAL_CHALLENGE,
    },
    CharacterAttributeKey.INTELLIGENCE: {
        AttributeEvidenceSource.TRAINING,
        AttributeEvidenceSource.MENTAL_STUDY,
        AttributeEvidenceSource.REAL_CHALLENGE,
    },
    CharacterAttributeKey.WISDOM: {
        AttributeEvidenceSource.TRAINING,
        AttributeEvidenceSource.MENTAL_STUDY,
        AttributeEvidenceSource.PERCEPTIVE_EXPERIENCE,
        AttributeEvidenceSource.REAL_CHALLENGE,
    },
    CharacterAttributeKey.ENDURANCE: {
        AttributeEvidenceSource.TRAINING,
        AttributeEvidenceSource.PHYSICAL_EXERTION,
        AttributeEvidenceSource.RECOVERY_CHALLENGE,
        AttributeEvidenceSource.REAL_CHALLENGE,
    },
    # Sorte é exclusiva do protagonista e não cresce por treino rotineiro.
    CharacterAttributeKey.LUCK: set(),
}


@dataclass(frozen=True)
class AttributeDevelopmentAward:
    attribute: CharacterAttribute
    record: AttributeEvidenceRecord
    repetition_multiplier: float
    increases: int


def ensure_attribute_catalog(db: Session) -> list[AttributeDefinition]:
    definitions: list[AttributeDefinition] = []
    for key, (name, description) in ATTRIBUTE_CATALOG.items():
        definition = db.get(AttributeDefinition, key.value)
        if definition is None:
            definition = AttributeDefinition(
                key=key.value,
                name=name,
                description=description,
            )
            db.add(definition)
        definitions.append(definition)
    db.flush()
    return definitions


def list_character_attributes(
    db: Session,
    character_id: str,
) -> list[CharacterAttribute]:
    return (
        db.query(CharacterAttribute)
        .join(AttributeDefinition)
        .filter(CharacterAttribute.character_id == character_id)
        .order_by(AttributeDefinition.name)
        .all()
    )


def get_character_attribute(
    db: Session,
    character_id: str,
    key: CharacterAttributeKey,
) -> CharacterAttribute:
    if not isinstance(key, CharacterAttributeKey):
        raise ValueError("Invalid character attribute key.")
    attribute = (
        db.query(CharacterAttribute)
        .filter(
            CharacterAttribute.character_id == character_id,
            CharacterAttribute.key == key.value,
        )
        .one_or_none()
    )
    if attribute is None:
        raise ValueError("Character does not possess the requested base attribute.")
    return attribute


def attribute_development_to_next_value(value: int) -> float:
    """Isolated foundation curve; combat formulas remain deferred to Phase 9."""
    return 10.0 + max(0, value - 10) * 2.5


def attribute_check_modifier(value: int) -> int:
    """Moderate d20 contribution: an attribute helps without replacing expertise."""
    return (value - 10) // 2


def award_attribute_development(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    attribute_key: CharacterAttributeKey,
    source: AttributeEvidenceSource,
    evidence_key: str,
    context_key: str,
    amount: float,
) -> AttributeDevelopmentAward:
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    if not isinstance(attribute_key, CharacterAttributeKey):
        raise ValueError("Invalid character attribute key.")
    if not isinstance(source, AttributeEvidenceSource):
        raise ValueError("Invalid attribute evidence source.")
    if source not in _ALLOWED_SOURCES[attribute_key]:
        if attribute_key == CharacterAttributeKey.LUCK:
            raise ValueError("Luck does not grow through ordinary training evidence.")
        raise ValueError("Evidence source is not relevant to this attribute.")
    if not isfinite(amount) or amount <= 0:
        raise ValueError("Attribute development amount must be finite and positive.")
    normalized_evidence = evidence_key.strip().lower()
    normalized_context = context_key.strip().lower()
    if not normalized_evidence:
        raise ValueError("Attribute evidence key is required.")
    if not normalized_context:
        raise ValueError("Attribute evidence context is required.")

    attribute = get_character_attribute(db, character.id, attribute_key)
    world_minute = get_world_time(db, campaign_id).total_minutes()
    cutoff = world_minute - ATTRIBUTE_REPETITION_WINDOW_MINUTES
    repetition_count = (
        db.query(AttributeEvidenceRecord)
        .filter(
            AttributeEvidenceRecord.character_id == character.id,
            AttributeEvidenceRecord.attribute_key == attribute_key.value,
            AttributeEvidenceRecord.source == source.value,
            AttributeEvidenceRecord.evidence_key == normalized_evidence,
            AttributeEvidenceRecord.world_minute >= cutoff,
        )
        .count()
    )
    repetition_multiplier = 1.0 / (repetition_count + 1)
    awarded_amount = amount * repetition_multiplier
    attribute.development += awarded_amount

    record = AttributeEvidenceRecord(
        campaign_id=campaign_id,
        character_id=character.id,
        attribute_key=attribute_key.value,
        source=source.value,
        evidence_key=normalized_evidence,
        context_key=normalized_context,
        base_amount=amount,
        awarded_amount=awarded_amount,
        repetition_count=repetition_count,
        world_minute=world_minute,
    )
    db.add(record)

    increases = 0
    while attribute.development >= attribute_development_to_next_value(
        attribute.value
    ):
        required = attribute_development_to_next_value(attribute.value)
        attribute.development -= required
        previous_value = attribute.value
        attribute.value += 1
        increases += 1
        log_event(
            db,
            campaign_id,
            EventType.PLAYER_ATTRIBUTE_INCREASED,
            actor_type="character",
            actor_id=character.id,
            payload={
                "attribute_key": attribute.key,
                "attribute_name": attribute.definition.name,
                "previous_value": previous_value,
                "new_value": attribute.value,
            },
        )
        if attribute_key in {
            CharacterAttributeKey.VITALITY,
            CharacterAttributeKey.ENDURANCE,
        }:
            from app.game.resources.service import (
                apply_attribute_resource_growth,
            )

            apply_attribute_resource_growth(
                db,
                campaign_id,
                character,
                attribute_key=attribute_key,
                attribute_value=attribute.value,
            )
    db.flush()
    return AttributeDevelopmentAward(
        attribute=attribute,
        record=record,
        repetition_multiplier=repetition_multiplier,
        increases=increases,
    )
