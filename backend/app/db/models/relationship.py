from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class CharacterNPCRelationship(Base):
    """Authoritative relationship state derived only from structured interactions."""

    __tablename__ = "character_npc_relationships"
    __table_args__ = (
        UniqueConstraint(
            "character_id", "npc_id", name="uq_character_npc_relationship_pair"
        ),
        Index("ix_character_npc_relationship_campaign", "campaign_id", "character_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("rel"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    npc_id: Mapped[str] = mapped_column(ForeignKey("npcs.id"), nullable=False)
    familiarity: Mapped[int] = mapped_column(Integer, default=0)
    trust: Mapped[int] = mapped_column(Integer, default=0)
    affinity: Mapped[int] = mapped_column(Integer, default=0)
    last_interaction_minute: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )

class CharacterSimulatedPlayerRelationship(Base):
    """
    Authoritative relationship state between the protagonist
    and one persistent transported person.
    """

    __tablename__ = "character_simulated_player_relationships"

    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "simulated_player_id",
            name="uq_character_simulated_player_relationship_pair",
        ),
        Index(
            "ix_character_simulated_player_relationship_campaign",
            "campaign_id",
            "character_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("rel"),
    )

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )

    simulated_player_id: Mapped[str] = mapped_column(
        ForeignKey("simulated_players.id"),
        nullable=False,
    )

    familiarity: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    trust: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    affinity: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    last_interaction_minute: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(
            tzinfo=None
        ),
    )


class SimulatedPlayerRelationship(Base):
    """Ordered, persistent social state between two transported people."""

    __tablename__ = "simulated_player_relationships"
    __table_args__ = (
        UniqueConstraint(
            "first_player_id",
            "second_player_id",
            name="uq_simulated_player_relationship_pair",
        ),
        Index(
            "ix_simulated_player_relationship_campaign",
            "campaign_id",
            "first_player_id",
            "second_player_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("rel")
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False
    )
    first_player_id: Mapped[str] = mapped_column(
        ForeignKey("simulated_players.id"), nullable=False
    )
    second_player_id: Mapped[str] = mapped_column(
        ForeignKey("simulated_players.id"), nullable=False
    )
    familiarity: Mapped[int] = mapped_column(Integer, default=0)
    trust: Mapped[int] = mapped_column(Integer, default=0)
    affinity: Mapped[int] = mapped_column(Integer, default=0)
    last_interaction_minute: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
