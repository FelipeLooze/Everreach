"""Phase 14 — shared money-movement helper for any EconomicActorType.

An economic actor's money lives in one of two places depending on its
type: Organization.treasury (Phase 13J/14A) for ORGANIZATION, or a
CurrencyHolding (Phase 14A) for CHARACTER/NPC/SIMULATED_PLAYER. Several
Phase 14 subphases need to pay or charge "whichever kind of actor this
is" (wages, business capital, business operations) — this is the one
place that branches, so nothing re-implements the branch per subphase.
"""

from sqlalchemy.orm import Session

from app.core.enums import EconomicActorType
from app.db.models.organization import Organization
from app.game.economy.currency import CurrencyError
from app.game.economy.wallet import deposit as wallet_deposit
from app.game.economy.wallet import get_or_create_holding
from app.game.economy.wallet import withdraw as wallet_withdraw
from app.game.organizations.assets import deposit_funds, withdraw_funds
from app.game.organizations.service import OrganizationError


class ActorFundsError(Exception):
    pass


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
    else:
        holding = get_or_create_holding(db, campaign_id, actor_type, actor_id)
        wallet_deposit(db, holding, amount, reason=reason)
