"""Phase 13J — Organization Resources & Assets.

Guildmaster owns sword != Guild owns sword. assign_item_to_organization
links an existing ItemInstance (Phase 10 — reused, not duplicated) to its
beneficial organizational owner via the OrganizationAsset overlay (see
that model's docstring for why this is an overlay rather than extending
ItemInstance.owner_type directly — a real Phase 10 constraint conflict,
reported rather than silently worked around).

treasury is deliberately simple: a single authoritative balance with
every change logged and reasoned — not a ledger/accounting system. Full
economy is Phase 14's; this only makes organizational ownership possible.
"""

from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.item import ItemInstance
from app.db.models.organization import Organization, OrganizationAsset
from app.game.organizations.service import OrganizationError
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


def assign_item_to_organization(
    db: Session, organization: Organization, item: ItemInstance
) -> OrganizationAsset:
    existing = (
        db.query(OrganizationAsset)
        .filter(OrganizationAsset.item_instance_id == item.id)
        .first()
    )
    if existing is not None:
        if existing.organization_id == organization.id:
            return existing
        raise OrganizationError("Este item já pertence a outra organização.")

    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    asset = OrganizationAsset(
        organization_id=organization.id,
        item_instance_id=item.id,
        acquired_world_minute=world_minute,
    )
    db.add(asset)
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_ASSET_ASSIGNED,
        actor_type="organization",
        actor_id=organization.id,
        payload={"item_instance_id": item.id},
        occurred_world_minute=world_minute,
    )
    return asset


def unassign_item_from_organization(db: Session, asset: OrganizationAsset) -> None:
    organization = db.get(Organization, asset.organization_id)
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    item_instance_id = asset.item_instance_id
    db.delete(asset)
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_ASSET_UNASSIGNED,
        actor_type="organization",
        actor_id=organization.id,
        payload={"item_instance_id": item_instance_id},
        occurred_world_minute=world_minute,
    )


def organization_assets(db: Session, organization_id: str) -> list[ItemInstance]:
    return (
        db.query(ItemInstance)
        .join(OrganizationAsset, OrganizationAsset.item_instance_id == ItemInstance.id)
        .filter(OrganizationAsset.organization_id == organization_id)
        .all()
    )


def deposit_funds(db: Session, organization: Organization, amount: int, *, reason: str) -> Organization:
    """amount is in Bronze (Phase 14A's canonical smallest unit) — always
    an integer; there is no fractional Bronze."""
    if amount <= 0:
        raise OrganizationError("O valor depositado precisa ser positivo.")
    return _change_funds(db, organization, amount, reason=reason)


def withdraw_funds(db: Session, organization: Organization, amount: int, *, reason: str) -> Organization:
    if amount <= 0:
        raise OrganizationError("O valor retirado precisa ser positivo.")
    if amount > organization.treasury:
        raise OrganizationError(
            f"'{organization.name}' não tem fundos suficientes "
            f"({organization.treasury} bronze disponíveis, {amount} solicitados)."
        )
    return _change_funds(db, organization, -amount, reason=reason)


def _change_funds(
    db: Session, organization: Organization, delta: int, *, reason: str
) -> Organization:
    if not reason.strip():
        raise OrganizationError("Uma mudança no tesouro precisa de um motivo explicável.")
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    organization.treasury += delta
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_FUNDS_CHANGED,
        actor_type="organization",
        actor_id=organization.id,
        payload={"delta": delta, "reason": reason, "new_balance": organization.treasury},
        occurred_world_minute=world_minute,
    )
    return organization
