from sqlalchemy.orm import Session

from app.db.models.skill import CharacterSkill, Skill


def get_or_create_skill(db: Session, name: str, category: str = "general") -> Skill:
    skill = db.query(Skill).filter(Skill.name == name).first()
    if skill:
        return skill
    skill = Skill(name=name, category=category)
    db.add(skill)
    db.flush()
    return skill


def grant_skill(db: Session, character_id: str, skill_name: str, category: str = "general") -> CharacterSkill:
    skill = get_or_create_skill(db, skill_name, category)
    existing = (
        db.query(CharacterSkill)
        .filter(CharacterSkill.character_id == character_id, CharacterSkill.skill_id == skill.id)
        .first()
    )
    if existing:
        return existing

    cskill = CharacterSkill(character_id=character_id, skill_id=skill.id, mastery=0)
    db.add(cskill)
    db.flush()
    return cskill


def increase_mastery(character_skill: CharacterSkill, amount: float) -> None:
    """Mastery is uncapped — 100 is a traditional reference point, not a hard limit."""
    if amount <= 0:
        return
    character_skill.mastery += amount
