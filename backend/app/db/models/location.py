from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ConnectionType, DiscoveryStatus
from app.core.ids import generate_id
from app.db.base import Base


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("loc"))
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), nullable=False)
    subregion_id: Mapped[str | None] = mapped_column(ForeignKey("subregions.id"), nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, default="generic")
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String, default="")
    discovery_status: Mapped[str] = mapped_column(String, default=DiscoveryStatus.UNKNOWN)

    # Phase 15F — Three-Tier Materialization Model. 1 = fully materialized
    # at generation (macro structure). 2 = exists as a named stub only
    # (minor settlements/POIs — filled in later, see Phase 15N/15P
    # content-on-demand). 3 = micro detail (interiors), materialized only
    # on demand. Every Location generated so far in Phase 15 is Tier 1
    # except Phase 15F's minor settlement stubs.
    materialization_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class LocationConnection(Base):
    __tablename__ = "location_connections"
    __table_args__ = (
        Index("ix_location_connection_origin_active", "from_location_id", "active"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("conn"))
    from_location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    to_location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    direction: Mapped[str | None] = mapped_column(String, nullable=True)
    connection_type: Mapped[str] = mapped_column(String, default=ConnectionType.PATH)
    distance: Mapped[float] = mapped_column(Float, default=1.0)
    danger: Mapped[int] = mapped_column(Integer, default=0)
    travel_time_modifier: Mapped[float] = mapped_column(Float, default=1.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LocationFeature(Base):
    """A concrete, directly perceptible feature of a location."""

    __tablename__ = "location_features"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("feature"))
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    visible: Mapped[bool] = mapped_column(Boolean, default=True)

class CharacterLocationDiscovery(Base):
    """What one protagonist knows about one location.

    Absence of a row means UNKNOWN.
    Discovery belongs to the character, never to the world location itself.
    """

    __tablename__ = "character_location_discoveries"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "location_id",
            name="uq_character_location_discovery",
        ),
        Index(
            "ix_character_location_discovery_character_status",
            "character_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("locdisc"),
    )

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )

    location_id: Mapped[str] = mapped_column(
        ForeignKey("locations.id"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String,
        default=DiscoveryStatus.RUMORED,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )

    discovered_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    visited_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    mapped_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

class CharacterConnectionDiscovery(Base):
    """What one protagonist knows about one physical connection.

    Absence of a row means the character does not know this route.
    """

    __tablename__ = "character_connection_discoveries"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "connection_id",
            name="uq_character_connection_discovery",
        ),
        Index(
            "ix_character_connection_discovery_character",
            "character_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("conndisc"),
    )

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )

    connection_id: Mapped[str] = mapped_column(
        ForeignKey("location_connections.id"),
        nullable=False,
    )

    discovered_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )