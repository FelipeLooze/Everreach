from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
from app.core.enums import (
    CharacterAttributeKey,
    CharacterResourceKey,
    CombatActionType,
    TechniqueLearningState,
    TechniqueOrigin,
    TechniqueType,
)
from app.db.base import Base


class Skill(Base):
    """Catalog of known skill types. New skills can be inserted freely — no fixed tree."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("skill"))
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    category: Mapped[str] = mapped_column(String, default="general")


class CharacterSkill(Base):
    """A character's mastery of a skill. Mastery is uncapped (100 is not a hard ceiling)."""

    __tablename__ = "character_skills"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("cskill"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), nullable=False)
    mastery: Mapped[float] = mapped_column(Float, default=0)

    skill: Mapped["Skill"] = relationship()


class Technique(Base):
    """A specific technique tied to a skill (e.g. Parry under Swordsmanship)."""

    __tablename__ = "techniques"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("tech"))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    technique_type: Mapped[str] = mapped_column(
        String,
        default=TechniqueType.PHYSICAL.value,
        nullable=False,
    )

    domains: Mapped[list["TechniqueDomain"]] = relationship(
        cascade="all, delete-orphan",
        order_by="TechniqueDomain.domain_key",
    )
    combat_profile: Mapped["CombatTechniqueProfile | None"] = relationship(
        cascade="all, delete-orphan",
        uselist=False,
    )


class TechniqueDomain(Base):
    """A capability domain that a technique mechanically integrates."""

    __tablename__ = "technique_domains"

    technique_id: Mapped[str] = mapped_column(
        ForeignKey("techniques.id"),
        primary_key=True,
    )
    domain_key: Mapped[str] = mapped_column(
        ForeignKey("domain_definitions.key"),
        primary_key=True,
    )


class CharacterTechnique(Base):
    """A character's relationship with a technique — not just whether they
    know it, but how far along: AWARE (knows it exists) → LEARNING (actively
    developing it) → LEARNED (can attempt it). Absence of a row means UNKNOWN.
    See TechniqueLearningState/TechniqueOrigin for that state machine.
    `mastery` is a separate, continuous axis that only matters once LEARNED —
    how reliably the technique is executed, not a level and not more damage.
    See app.game.skills.technique_mastery for the player-facing tier this
    maps to and the one mechanical effect it has."""

    __tablename__ = "character_techniques"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("ctech"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    technique_id: Mapped[str] = mapped_column(ForeignKey("techniques.id"), nullable=False)
    learning_state: Mapped[str] = mapped_column(
        String,
        default=TechniqueLearningState.LEARNED.value,
        nullable=False,
    )
    origin: Mapped[str] = mapped_column(
        String,
        default=TechniqueOrigin.SELF_DISCOVERED.value,
        nullable=False,
    )
    world_minute: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mastery: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    technique: Mapped["Technique"] = relationship()


class CombatTechniqueProfile(Base):
    """Immutable authoritative combat mechanics for an otherwise narrative technique."""

    __tablename__ = "combat_technique_profiles"

    technique_id: Mapped[str] = mapped_column(
        ForeignKey("techniques.id"),
        primary_key=True,
    )
    action_type: Mapped[str] = mapped_column(
        String,
        default=CombatActionType.MELEE_ATTACK.value,
        nullable=False,
    )
    attack_attribute: Mapped[str] = mapped_column(
        String,
        default=CharacterAttributeKey.STRENGTH.value,
        nullable=False,
    )
    resource_key: Mapped[str] = mapped_column(
        String,
        default=CharacterResourceKey.STAMINA.value,
        nullable=False,
    )
    resource_cost: Mapped[float] = mapped_column(Float, nullable=False)
    base_damage_dice: Mapped[int] = mapped_column(Integer, nullable=False)
    damage_die_sides: Mapped[int] = mapped_column(Integer, nullable=False)
    damage_attribute: Mapped[str] = mapped_column(String, nullable=False)
    damage_type: Mapped[str] = mapped_column(
        String,
        default="PHYSICAL",
        nullable=False,
    )
    condition_type: Mapped[str | None] = mapped_column(String, nullable=True)
    condition_duration_turns: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    required_weapon_family: Mapped[str | None] = mapped_column(String, nullable=True)


class TechniqueUseRecord(Base):
    """Idempotent mechanical result of one explicitly selected technique use."""

    __tablename__ = "technique_use_records"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "character_id",
            "action_key",
            name="uq_technique_use_action",
        ),
        Index(
            "ix_technique_use_character_time",
            "character_id",
            "world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("tuse"),
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    technique_id: Mapped[str] = mapped_column(
        ForeignKey("techniques.id"),
        nullable=False,
    )
    action_key: Mapped[str] = mapped_column(String, nullable=False)
    roll: Mapped[int] = mapped_column(Integer, nullable=False)
    modifier: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    dc: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    world_minute: Mapped[int] = mapped_column(Integer, nullable=False)

    technique: Mapped["Technique"] = relationship()
