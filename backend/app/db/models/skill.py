from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
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


class CharacterTechnique(Base):
    __tablename__ = "character_techniques"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("ctech"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    technique_id: Mapped[str] = mapped_column(ForeignKey("techniques.id"), nullable=False)

    technique: Mapped["Technique"] = relationship()
