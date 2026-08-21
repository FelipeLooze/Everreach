"""Phase 14A — Currency Foundation: physically-held money.

CurrencyHolding represents Bronze actually held by a character/NPC/
simulated player — never one row per coin (see the model's docstring).
transfer is the raw movement primitive only: withdraw from one holding,
deposit into another, atomically, with no price/item logic at all — that
belongs to Phase 14C's buy/sell/trade transactions, built on top of this.

owner_type reuses CombatActorType; Organization money stays on
Organization.treasury (Phase 13J, now integer Bronze — see
app.game.organizations.assets.deposit_funds/withdraw_funds) rather than
living in this table — Organizations are not a CombatActorType and were
deliberately not folded in here.
"""

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, EventType
from app.db.models.currency import CurrencyHolding
from app.game.economy.currency import CurrencyError
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


def get_or_create_holding(
    db: Session,
    campaign_id: str,
    owner_type: CombatActorType,
    owner_id: str,
    *,
    container_item_instance_id: str | None = None,
) -> CurrencyHolding:
    holding = (
        db.query(CurrencyHolding)
        .filter(
            CurrencyHolding.owner_type == owner_type,
            CurrencyHolding.owner_id == owner_id,
            CurrencyHolding.container_item_instance_id == container_item_instance_id,
        )
        .first()
    )
    if holding is not None:
        return holding
    holding = CurrencyHolding(
        campaign_id=campaign_id,
        owner_type=owner_type,
        owner_id=owner_id,
        container_item_instance_id=container_item_instance_id,
        amount_bronze=0,
    )
    db.add(holding)
    db.flush()
    return holding


def deposit(db: Session, holding: CurrencyHolding, amount_bronze: int, *, reason: str) -> CurrencyHolding:
    if not isinstance(amount_bronze, int) or isinstance(amount_bronze, bool) or amount_bronze <= 0:
        raise CurrencyError("O valor depositado precisa ser um inteiro positivo de Bronze.")
    if not reason.strip():
        raise CurrencyError("Um depósito precisa de um motivo explicável.")

    world_minute = get_world_time(db, holding.campaign_id).total_minutes()
    holding.amount_bronze += amount_bronze
    db.flush()

    log_event(
        db,
        holding.campaign_id,
        EventType.CURRENCY_DEPOSITED,
        actor_type=holding.owner_type.lower(),
        actor_id=holding.owner_id,
        payload={"holding_id": holding.id, "amount_bronze": amount_bronze, "reason": reason},
        occurred_world_minute=world_minute,
    )
    return holding


def withdraw(db: Session, holding: CurrencyHolding, amount_bronze: int, *, reason: str) -> CurrencyHolding:
    if not isinstance(amount_bronze, int) or isinstance(amount_bronze, bool) or amount_bronze <= 0:
        raise CurrencyError("O valor retirado precisa ser um inteiro positivo de Bronze.")
    if not reason.strip():
        raise CurrencyError("Uma retirada precisa de um motivo explicável.")
    if amount_bronze > holding.amount_bronze:
        raise CurrencyError(
            f"Fundos insuficientes ({holding.amount_bronze} bronze disponíveis, "
            f"{amount_bronze} solicitados)."
        )

    world_minute = get_world_time(db, holding.campaign_id).total_minutes()
    holding.amount_bronze -= amount_bronze
    db.flush()

    log_event(
        db,
        holding.campaign_id,
        EventType.CURRENCY_WITHDRAWN,
        actor_type=holding.owner_type.lower(),
        actor_id=holding.owner_id,
        payload={"holding_id": holding.id, "amount_bronze": amount_bronze, "reason": reason},
        occurred_world_minute=world_minute,
    )
    return holding


def transfer(
    db: Session,
    from_holding: CurrencyHolding,
    to_holding: CurrencyHolding,
    amount_bronze: int,
    *,
    reason: str,
) -> None:
    """The raw movement primitive: no value is created or destroyed —
    withdrawing from one holding and depositing into another are the
    same conceptual event, logged once, not two independent transfers
    that happen to cancel out."""
    if from_holding.id == to_holding.id:
        raise CurrencyError("Uma transferência precisa de uma origem e um destino diferentes.")
    if not isinstance(amount_bronze, int) or isinstance(amount_bronze, bool) or amount_bronze <= 0:
        raise CurrencyError("O valor transferido precisa ser um inteiro positivo de Bronze.")
    if not reason.strip():
        raise CurrencyError("Uma transferência precisa de um motivo explicável.")
    if amount_bronze > from_holding.amount_bronze:
        raise CurrencyError(
            f"Fundos insuficientes para a transferência ({from_holding.amount_bronze} bronze "
            f"disponíveis, {amount_bronze} solicitados)."
        )

    world_minute = get_world_time(db, from_holding.campaign_id).total_minutes()
    from_holding.amount_bronze -= amount_bronze
    to_holding.amount_bronze += amount_bronze
    db.flush()

    log_event(
        db,
        from_holding.campaign_id,
        EventType.CURRENCY_TRANSFERRED,
        actor_type=from_holding.owner_type.lower(),
        actor_id=from_holding.owner_id,
        payload={
            "from_holding_id": from_holding.id,
            "to_holding_id": to_holding.id,
            "to_owner_type": to_holding.owner_type,
            "to_owner_id": to_holding.owner_id,
            "amount_bronze": amount_bronze,
            "reason": reason,
        },
        occurred_world_minute=world_minute,
    )


def total_carried_by_owner(db: Session, owner_type: CombatActorType, owner_id: str) -> int:
    """Sum across every holding (personally carried plus any containers)
    for this owner — a convenience total, not a new source of truth."""
    holdings = (
        db.query(CurrencyHolding)
        .filter(CurrencyHolding.owner_type == owner_type, CurrencyHolding.owner_id == owner_id)
        .all()
    )
    return sum(holding.amount_bronze for holding in holdings)
