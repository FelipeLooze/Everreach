from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class CurrencyHolding(Base):
    """Phase 14A — an amount of physically-held money, in Bronze (the
    canonical smallest unit: 100 Bronze = 1 Silver, 100 Silver = 1 Gold —
    see app.game.economy.currency). owner_type reuses CombatActorType
    (CHARACTER/NPC/SIMULATED_PLAYER) — the same actor vocabulary Group
    and OrganizationMember already use (Phase 13), rather than a new
    enum. Organization money stays on Organization.treasury (Phase 13J,
    now integer Bronze too) — Organizations are not an owner_type here.

    container_item_instance_id is optional: None means the money is
    carried personally (no physical "wallet" item is required to exist);
    set it to reuse an existing Phase 10 container ItemInstance (a chest,
    a pouch) to represent money actually sitting inside that real world
    object. Money is never one row per coin — one CurrencyHolding row
    accumulates per (owner, container) pair."""

    __tablename__ = "currency_holdings"
    __table_args__ = (
        UniqueConstraint(
            "owner_type", "owner_id", "container_item_instance_id",
            name="uq_currency_holding_owner_container",
        ),
        CheckConstraint("amount_bronze >= 0", name="ck_currency_holding_non_negative"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("wallet"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    owner_type: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    container_item_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("item_instances.id"), nullable=True
    )
    amount_bronze: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
