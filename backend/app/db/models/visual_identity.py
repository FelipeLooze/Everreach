from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class VisualIdentity(Base):
    """Phase 21C — Structured Visual Specification Foundation.

    ONE reusable, polymorphic table for every entity kind's visual
    data (NPC/item/creature/location/settlement/region/organization),
    the same overlay convention app.db.models.map.Map and
    app.db.models.settlement.Settlement already use, and the same
    (subject_kind, subject_id) addressing app.game.knowledge.geography
    already established — never a new "visual_identity" column bolted
    onto every existing entity table ("DO NOT pollute every database
    table with dozens of style fields", spec, mandatory).

    stable_json / current_json are the spec's mandatory split:
    STABLE VISUAL IDENTITY (long-lived — species, hair color, permanent
    scars, weapon family, architectural identity, ...) versus CURRENT
    VISUAL STATE (temporary — current clothing, dirt, damage, weather,
    ...). "Never mix stable identity and temporary state into one
    uncontrolled text field" (spec, mandatory) is enforced structurally
    by being two separate columns, not a convention someone can forget.

    Deliberately no per-entity-kind columns or schema here: WHICH keys
    each dict may hold (hair_color, eye_color, material, ...) is each
    concrete entity kind's own vocabulary, defined by its own subphase
    (21D Item, 21E NPC, 21F Creature, ...) — this table only provides
    the shared storage/versioning primitive every one of them reuses.

    campaign_id is nullable: some subjects (ItemDefinition, the shared
    mechanical item catalog — see app.db.models.item) are campaign-
    global, not per-campaign, exactly like the item catalog itself.
    """

    __tablename__ = "visual_identities"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "subject_kind", "subject_id", name="uq_visual_identity_subject"
        ),
        Index("ix_visual_identity_subject", "subject_kind", "subject_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("visual"))
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    subject_kind: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[str] = mapped_column(String, nullable=False)

    stable_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    current_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
