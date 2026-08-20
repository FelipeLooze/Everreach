from sqlalchemy.orm import Session

from app.core.enums import ClassOfferStatus, EventType
from app.db.models.campaign import Campaign
from app.db.models.character import Character
from app.db.models.character_class import (
    CharacterClassOffer,
    ClassDefinition,
    ClassDefinitionDomain,
)
from app.services.event_log import log_event


class ClassChoiceError(ValueError):
    pass


def create_class_definition(
    db: Session,
    campaign_id: str,
    name: str,
    description: str,
    *,
    identity: str = "",
    theme: str = "",
    generation_key: str | None = None,
    domain_keys: tuple[str, ...] = (),
) -> ClassDefinition:
    if db.get(Campaign, campaign_id) is None:
        raise ValueError("Campaign does not exist.")
    normalized_name = " ".join(name.split())
    normalized_description = " ".join(description.split())
    normalized_identity = " ".join(identity.split())
    normalized_theme = " ".join(theme.split())
    if not normalized_name:
        raise ValueError("Class name is required.")
    if not normalized_description:
        raise ValueError("Class description is required.")

    if generation_key is not None:
        existing_by_path = (
            db.query(ClassDefinition)
            .filter(
                ClassDefinition.campaign_id == campaign_id,
                ClassDefinition.generation_key == generation_key,
            )
            .first()
        )
        if existing_by_path is not None:
            return existing_by_path

    existing = (
        db.query(ClassDefinition)
        .filter(
            ClassDefinition.campaign_id == campaign_id,
            ClassDefinition.name == normalized_name,
        )
        .first()
    )
    if existing is not None:
        if (
            generation_key is not None
            and existing.generation_key != generation_key
        ):
            raise ValueError(
                "Generated class name is already used by another class path."
            )
        return existing

    class_definition = ClassDefinition(
        campaign_id=campaign_id,
        name=normalized_name,
        description=normalized_description,
        identity=normalized_identity,
        theme=normalized_theme,
        generation_key=generation_key,
    )
    db.add(class_definition)
    db.flush()
    for domain_key in sorted(set(domain_keys)):
        db.add(
            ClassDefinitionDomain(
                class_definition_id=class_definition.id,
                domain_key=domain_key,
            )
        )
    db.flush()
    return class_definition


def make_pending_class_offers_available(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    safe_to_notify: bool,
) -> list[CharacterClassOffer]:
    """Reveal pending offers only when the authoritative caller marks a safe moment."""
    pending = (
        db.query(CharacterClassOffer)
        .filter(
            CharacterClassOffer.character_id == character.id,
            CharacterClassOffer.status == ClassOfferStatus.PENDING.value,
        )
        .order_by(CharacterClassOffer.created_at, CharacterClassOffer.id)
        .all()
    )
    return [
        make_class_offer_available(
            db,
            campaign_id,
            character,
            offer,
            safe_to_notify=safe_to_notify,
        )
        for offer in pending
    ]


def create_class_offer(
    db: Session,
    campaign_id: str,
    character: Character,
    class_definition: ClassDefinition,
) -> CharacterClassOffer:
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    if class_definition.campaign_id != campaign_id:
        raise ValueError("Class does not belong to campaign.")

    existing = (
        db.query(CharacterClassOffer)
        .filter(
            CharacterClassOffer.character_id == character.id,
            CharacterClassOffer.class_definition_id == class_definition.id,
        )
        .first()
    )
    if existing is not None:
        return existing

    offer = CharacterClassOffer(
        character_id=character.id,
        class_definition_id=class_definition.id,
        status=ClassOfferStatus.PENDING.value,
    )
    db.add(offer)
    db.flush()
    return offer


def make_class_offer_available(
    db: Session,
    campaign_id: str,
    character: Character,
    offer: CharacterClassOffer,
    *,
    safe_to_notify: bool,
) -> CharacterClassOffer:
    _validate_offer(db, campaign_id, character, offer)
    if not safe_to_notify or offer.status != ClassOfferStatus.PENDING.value:
        return offer

    offer.status = ClassOfferStatus.AVAILABLE.value
    log_event(
        db,
        campaign_id,
        EventType.PLAYER_CLASS_OFFERED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "offer_id": offer.id,
            "class_id": offer.class_definition.id,
            "class_name": offer.class_definition.name,
        },
    )
    db.flush()
    return offer


def delay_class_offer(
    db: Session,
    campaign_id: str,
    character: Character,
    offer: CharacterClassOffer,
) -> CharacterClassOffer:
    _validate_offer(db, campaign_id, character, offer)
    if offer.status == ClassOfferStatus.DELAYED.value:
        return offer
    if offer.status != ClassOfferStatus.AVAILABLE.value:
        raise ClassChoiceError("Only an available class offer can be delayed.")

    offer.status = ClassOfferStatus.DELAYED.value
    log_event(
        db,
        campaign_id,
        EventType.PLAYER_CLASS_OFFER_DELAYED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "offer_id": offer.id,
            "class_id": offer.class_definition.id,
            "class_name": offer.class_definition.name,
        },
    )
    db.flush()
    return offer


def accept_class_offer(
    db: Session,
    campaign_id: str,
    character: Character,
    offer: CharacterClassOffer,
) -> ClassDefinition:
    _validate_offer(db, campaign_id, character, offer)
    if (
        offer.status == ClassOfferStatus.ACCEPTED.value
        and character.active_class_id == offer.class_definition_id
    ):
        return offer.class_definition
    if offer.status not in {
        ClassOfferStatus.AVAILABLE.value,
        ClassOfferStatus.DELAYED.value,
    }:
        raise ClassChoiceError("This class offer is not available for acceptance.")
    if character.active_class_id is not None:
        raise ClassChoiceError("Character already has an active class.")

    character.active_class_id = offer.class_definition_id
    offer.status = ClassOfferStatus.ACCEPTED.value
    log_event(
        db,
        campaign_id,
        EventType.PLAYER_CLASS_ACCEPTED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "offer_id": offer.id,
            "class_id": offer.class_definition.id,
            "class_name": offer.class_definition.name,
        },
    )
    db.flush()
    return offer.class_definition


def get_active_class(
    db: Session,
    character: Character,
) -> ClassDefinition | None:
    if character.active_class_id is None:
        return None
    return db.get(ClassDefinition, character.active_class_id)


def list_visible_class_offers(
    db: Session,
    character_id: str,
) -> list[CharacterClassOffer]:
    return (
        db.query(CharacterClassOffer)
        .filter(
            CharacterClassOffer.character_id == character_id,
            CharacterClassOffer.status.in_(
                [
                    ClassOfferStatus.AVAILABLE.value,
                    ClassOfferStatus.DELAYED.value,
                ]
            ),
        )
        .order_by(CharacterClassOffer.created_at, CharacterClassOffer.id)
        .all()
    )


def _validate_offer(
    db: Session,
    campaign_id: str,
    character: Character,
    offer: CharacterClassOffer,
) -> None:
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    if offer.character_id != character.id:
        raise ValueError("Class offer does not belong to character.")
    class_definition = db.get(ClassDefinition, offer.class_definition_id)
    if class_definition is None or class_definition.campaign_id != campaign_id:
        raise ValueError("Class offer does not belong to campaign.")
