from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
from app.db.base import Base


class Profession(Base):
    """Extensible catalog of practical professions known by the backend."""

    __tablename__ = "professions"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("prof"),
    )
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")


class CharacterProfession(Base):
    """Profession progress that only exists after a character first earns XP."""

    __tablename__ = "character_professions"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "profession_id",
            name="uq_character_profession",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("cprof"),
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    profession_id: Mapped[str] = mapped_column(
        ForeignKey("professions.id"),
        nullable=False,
    )
    level: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[float] = mapped_column(Float, default=0.0)

    profession: Mapped["Profession"] = relationship()
