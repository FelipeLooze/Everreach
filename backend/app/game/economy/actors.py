"""Phase 14 — shared money-movement helper for any EconomicActorType.

An economic actor's money lives in one of three places depending on its
type: Organization.treasury (Phase 13J/14A) for ORGANIZATION,
Business.till_bronze (Phase 14K) for BUSINESS, or a CurrencyHolding
(Phase 14A) for CHARACTER/NPC/SIMULATED_PLAYER. Several Phase 14
subphases need to pay or charge "whichever kind of actor this is"
(wages, business capital, business operations) — this is the one place
that branches, so nothing re-implements the branch per subphase.

Business's own functions (app.game.economy.businesses) call INTO this
module for the actor-funds branch — this module deliberately does not
import from businesses.py, to avoid a cycle (businesses.py already
depends on this module for found_business's startup cost).
"""

from sqlalchemy.orm import Session

from app.core.enums import EconomicActorType, EventType
from app.db.models.business import Business
from app.db.models.organization import Organization
from app.game.economy.currency import CurrencyError
from app.game.economy.wallet import deposit as wallet_deposit
from app.game.economy.wallet import get_or_create_holding
from app.game.economy.wallet import withdraw as wallet_withdraw
from app.game.organizations.assets import deposit_funds, withdraw_funds
from app.game.organizations.service import OrganizationError
from app.services.event_log import log_event


class ActorFundsError(Exception):
    pass


def _get_business(db: Session, business_id: str) -> Business:
    business = db.get(Business, business_id)
    if business is None:
        raise ActorFundsError("O negócio não existe mais.")
    return business


def withdraw_from_actor(
    db: Session, actor_type: EconomicActorType, actor_id: str, campaign_id: str, amount: int, *, reason: str
) -> None:
    if actor_type == EconomicActorType.ORGANIZATION:
        organization = db.get(Organization, actor_id)
        if organization is None:
            raise ActorFundsError("A organização não existe mais.")
        try:
            withdraw_funds(db, organization, amount, reason=reason)
        except OrganizationError as exc:
            raise ActorFundsError(str(exc)) from exc
    elif actor_type == EconomicActorType.BUSINESS:
        business = _get_business(db, actor_id)
        if amount > business.till_bronze:
            raise ActorFundsError(
                f"'{business.name}' não tem fundos suficientes "
                f"({business.till_bronze} bronze disponíveis, {amount} solicitados)."
            )
        _change_business_till(db, business, -amount, reason=reason)
    else:
        holding = get_or_create_holding(db, campaign_id, actor_type, actor_id)
        try:
            wallet_withdraw(db, holding, amount, reason=reason)
        except CurrencyError as exc:
            raise ActorFundsError(str(exc)) from exc


def deposit_to_actor(
    db: Session, actor_type: EconomicActorType, actor_id: str, campaign_id: str, amount: int, *, reason: str
) -> None:
    if actor_type == EconomicActorType.ORGANIZATION:
        organization = db.get(Organization, actor_id)
        if organization is None:
            raise ActorFundsError("A organização não existe mais.")
        deposit_funds(db, organization, amount, reason=reason)
    elif actor_type == EconomicActorType.BUSINESS:
        business = _get_business(db, actor_id)
        _change_business_till(db, business, amount, reason=reason)
    else:
        holding = get_or_create_holding(db, campaign_id, actor_type, actor_id)
        wallet_deposit(db, holding, amount, reason=reason)


def _change_business_till(db: Session, business: Business, delta: int, *, reason: str) -> None:
    if not reason.strip():
        raise ActorFundsError("Uma mudança no caixa do negócio precisa de um motivo explicável.")
    business.till_bronze += delta
    db.flush()
    log_event(
        db, business.campaign_id, EventType.BUSINESS_FUNDS_CHANGED,
        actor_type="business", actor_id=business.id,
        payload={"delta": delta, "reason": reason, "new_balance": business.till_bronze},
    )
