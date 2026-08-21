from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ShopStatus
from app.core.ids import generate_id
from app.db.base import Base


class Shop(Base):
    """Phase 14G — a real world business operation, not a magical
    storefront menu. operator_type is restricted to CHARACTER/NPC (the
    only types Phase 10's ItemInstance.owner_type can hold) — the shop's
    stock is authoritative Phase 10 inventory owned by the operator, not
    a separate item universe. till_bronze is the shop's own finite funds
    (Phase 14A integer Bronze), deliberately separate from the
    operator's personal CurrencyHolding — a shop running out of money is
    a real, distinct fact from its operator being broke."""

    __tablename__ = "shops"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("shop"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    operator_type: Mapped[str] = mapped_column(String, nullable=False)
    operator_id: Mapped[str] = mapped_column(String, nullable=False)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default=ShopStatus.OPEN, nullable=False)
    till_bronze: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # JSON list of ItemType values this shop is willing to buy from
    # customers (Phase 14G's SHOP SPECIALIZATION) — empty means no
    # declared restriction (buys nothing unless explicitly listed; see
    # app.game.economy.shops.sell_to_shop).
    accepted_item_types_json: Mapped[str] = mapped_column(String, default="[]", nullable=False)


class ShopListing(Base):
    """One ItemInstance the shop is currently offering for sale — not
    ownership itself (the item's real ItemInstance.owner stays the
    operator, per Phase 10) but a marker of "this is shop stock, not the
    operator's personal belongings," at an optional asking price."""

    __tablename__ = "shop_listings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("listing"))
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), nullable=False)
    item_instance_id: Mapped[str] = mapped_column(
        ForeignKey("item_instances.id"), nullable=False, unique=True
    )
    asking_price_bronze: Mapped[int | None] = mapped_column(Integer, nullable=True)
