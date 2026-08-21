"""Phase 14L — Organization Economy Integration.

Reuses Organization Treasury (Phase 13J/14A) and OrganizationAsset
(Phase 13J) directly — no separate economic logic invented for
organizations. This module exists because Phase 14C's buy_item cannot
have an Organization as buyer/seller (ItemInstance ownership is
DB-constrained to CHARACTER/NPC, Phase 10) the same way Phase 13J
already had to work around for asset ownership — organization_purchase_
item/organization_sell_asset are the purchase/sale counterpart to that
same overlay, not a new item or currency system.

Everything else the spec lists for this subphase (organizations owning
money, owning businesses, hiring workers, sponsoring contracts, paying
rewards) already composes with zero new code once Organization became a
real EconomicActorType in Phase 14J/14K — see
test_organization_economy.py's integration tests for direct proof
(create_job/pay_wage/found_business already accept an Organization
unchanged).

ORGANIZATION NEEDS -> real economic action: Phase 13K's
propose_organization_action and Phase 13M's publish_organization_notice/
sponsor_quest are the existing bridges from a Need to a Notice/Quest;
this module adds the missing bridge from a Need to an actual purchase.
"""

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, EconomicActorType, ItemLocationType, ItemOwnerType
from app.db.models.item import ItemInstance
from app.db.models.organization import Organization, OrganizationAsset
from app.game.economy.actors import ActorFundsError, deposit_to_actor, withdraw_from_actor
from app.game.economy.pricing import resolve_market_price
from app.game.items.service import move_item_instance, set_item_owner
from app.game.organizations.assets import assign_item_to_organization, unassign_item_from_organization

_ITEM_OWNER_TYPES = (CombatActorType.CHARACTER, CombatActorType.NPC)


class OrganizationEconomyError(Exception):
    pass


def organization_purchase_item(
    db: Session,
    organization: Organization,
    item: ItemInstance,
    *,
    agent_type: CombatActorType,
    agent_id: str,
    seller_type: EconomicActorType,
    seller_id: str,
    price_bronze: int | None = None,
) -> int:
    """The organization pays from its treasury; the item is physically
    transferred to an agent (a character/NPC acting on the org's behalf
    — Phase 10 constrains ItemInstance ownership to CHARACTER/NPC) and
    then marked as the organization's beneficial asset (Phase 13J)."""
    if agent_type not in _ITEM_OWNER_TYPES:
        raise OrganizationEconomyError(
            "O agente que recebe o item precisa ser um personagem ou NPC (Fase 10)."
        )
    if item.owner_type != seller_type or item.owner_ref != seller_id:
        raise OrganizationEconomyError("O vendedor não possui este item.")

    price = price_bronze if price_bronze is not None else resolve_market_price(db, item)
    if price < 0:
        raise OrganizationEconomyError("O preço de uma compra não pode ser negativo.")

    if price > 0:
        try:
            withdraw_from_actor(
                db, EconomicActorType.ORGANIZATION, organization.id, organization.campaign_id, price,
                reason=f"Compra de {item.definition.name}.",
            )
        except ActorFundsError as exc:
            raise OrganizationEconomyError(str(exc)) from exc
        deposit_to_actor(
            db, seller_type, seller_id, organization.campaign_id, price,
            reason=f"Venda de {item.definition.name} para {organization.name}.",
        )

    set_item_owner(db, item, owner_type=ItemOwnerType(agent_type.value), owner_ref=agent_id)
    move_item_instance(db, item, location_type=ItemLocationType(agent_type.value), location_ref=agent_id)
    assign_item_to_organization(db, organization, item)
    return price


def organization_sell_asset(
    db: Session,
    organization: Organization,
    item: ItemInstance,
    *,
    buyer_type: CombatActorType,
    buyer_id: str,
    price_bronze: int | None = None,
) -> int:
    """The organization sells one of its own assets — proceeds go to its
    treasury, the item is physically transferred to the buyer, and it
    stops being the organization's asset. item must be one of the
    ItemInstance rows organization_assets(db, organization.id) returns."""
    if buyer_type not in _ITEM_OWNER_TYPES:
        raise OrganizationEconomyError(
            "Apenas personagens e NPCs podem possuir itens fisicamente (Fase 10)."
        )
    asset = db.query(OrganizationAsset).filter(OrganizationAsset.item_instance_id == item.id).first()
    if asset is None or asset.organization_id != organization.id:
        raise OrganizationEconomyError("Este item não é um ativo desta organização.")

    price = price_bronze if price_bronze is not None else resolve_market_price(db, item)
    if price < 0:
        raise OrganizationEconomyError("O preço de uma venda não pode ser negativo.")

    if price > 0:
        try:
            withdraw_from_actor(
                db, buyer_type, buyer_id, organization.campaign_id, price,
                reason=f"Compra de {item.definition.name} de {organization.name}.",
            )
        except ActorFundsError as exc:
            raise OrganizationEconomyError(str(exc)) from exc
        deposit_to_actor(
            db, EconomicActorType.ORGANIZATION, organization.id, organization.campaign_id, price,
            reason=f"Venda de {item.definition.name}.",
        )

    set_item_owner(db, item, owner_type=ItemOwnerType(buyer_type.value), owner_ref=buyer_id)
    move_item_instance(db, item, location_type=ItemLocationType(buyer_type.value), location_ref=buyer_id)
    unassign_item_from_organization(db, asset)
    return price
