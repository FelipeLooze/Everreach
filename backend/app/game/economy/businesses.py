"""Phase 14J — Businesses & Ownership.

No "[CREATE BUSINESS] -> business appears" button: found_business
requires the founder to actually spend real capital (startup_cost_bronze,
withdrawn via Phase 14J's shared withdraw_from_actor) when one is given
— the business emerging from an actual, affordable world action, not a
free declaration. A capital-free business (startup_cost_bronze=0, the
default) is legitimate too — an informal service needs no upfront money,
matching Phase 13E's own "not every organization needs the same
process" philosophy for business creation specifically.

OWNER != OPERATOR: an owner (individual or Organization, Phase 14L) may
hire someone else to run the business day to day — see
change_operator. Both individual and organization ownership are
supported without conflating operator with owner anywhere.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    BusinessStatus,
    BusinessType,
    CombatActorType,
    EconomicActorType,
    EventType,
)
from app.db.models.business import Business
from app.game.economy.actors import ActorFundsError, withdraw_from_actor
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


class BusinessError(Exception):
    pass


def found_business(
    db: Session,
    campaign_id: str,
    name: str,
    business_type: BusinessType,
    *,
    owner_type: EconomicActorType,
    owner_id: str,
    operator_type: CombatActorType | None = None,
    operator_id: str | None = None,
    location_id: str | None = None,
    startup_cost_bronze: int = 0,
) -> Business:
    if not name.strip():
        raise BusinessError("Um negócio precisa de um nome.")
    if (operator_type is None) != (operator_id is None):
        raise BusinessError("Operador precisa de tipo e id juntos, ou nenhum dos dois.")
    if startup_cost_bronze < 0:
        raise BusinessError("O custo inicial não pode ser negativo.")

    if startup_cost_bronze > 0:
        try:
            withdraw_from_actor(
                db, owner_type, owner_id, campaign_id, startup_cost_bronze,
                reason=f"Capital inicial para fundar '{name}'.",
            )
        except ActorFundsError as exc:
            raise BusinessError(str(exc)) from exc

    world_minute = get_world_time(db, campaign_id).total_minutes()
    business = Business(
        campaign_id=campaign_id,
        name=name,
        business_type=business_type,
        owner_type=owner_type,
        owner_id=owner_id,
        operator_type=operator_type,
        operator_id=operator_id,
        location_id=location_id,
        status=BusinessStatus.ACTIVE,
        founded_world_minute=world_minute,
    )
    db.add(business)
    db.flush()

    log_event(
        db, campaign_id, EventType.BUSINESS_FOUNDED,
        actor_type=owner_type.lower(), actor_id=owner_id,
        payload={"business_id": business.id, "business_type": business_type, "startup_cost_bronze": startup_cost_bronze},
        occurred_world_minute=world_minute,
    )
    return business


def change_operator(
    db: Session, business: Business, operator_type: CombatActorType | None, operator_id: str | None
) -> Business:
    if (operator_type is None) != (operator_id is None):
        raise BusinessError("Operador precisa de tipo e id juntos, ou nenhum dos dois.")
    world_minute = get_world_time(db, business.campaign_id).total_minutes()
    business.operator_type = operator_type
    business.operator_id = operator_id
    db.flush()

    log_event(
        db, business.campaign_id, EventType.BUSINESS_OPERATOR_CHANGED,
        actor_type="business", actor_id=business.id,
        payload={"new_operator_type": operator_type, "new_operator_id": operator_id},
        occurred_world_minute=world_minute,
    )
    return business


def close_business(db: Session, business: Business, *, reason: str = "") -> Business:
    if business.status == BusinessStatus.CLOSED:
        return business
    world_minute = get_world_time(db, business.campaign_id).total_minutes()
    business.status = BusinessStatus.CLOSED
    db.flush()

    log_event(
        db, business.campaign_id, EventType.BUSINESS_CLOSED,
        actor_type="business", actor_id=business.id,
        payload={"reason": reason},
        occurred_world_minute=world_minute,
    )
    return business


def businesses_owned_by(db: Session, owner_type: EconomicActorType, owner_id: str) -> list[Business]:
    return (
        db.query(Business)
        .filter(Business.owner_type == owner_type, Business.owner_id == owner_id)
        .all()
    )
