from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.game import dice
from app.game.skills.service import grant_skill
from app.core.enums import CharacterAttributeKey
from app.game.attributes.service import (
    attribute_check_modifier,
    get_character_attribute,
)

DEFAULT_DC = 12


@dataclass
class SkillCheckResult:
    skill_name: str
    dc: int
    roll: dice.RollResult
    success: bool
    critical: bool
    attribute_key: str | None = None
    attribute_modifier: int = 0


def resolve_skill_check(
    db: Session,
    character_id: str,
    skill_name: str,
    dc: int = DEFAULT_DC,
    *,
    attribute_key: CharacterAttributeKey | None = None,
) -> SkillCheckResult:
    """Generic d20 + mastery check. This intentionally does NOT resolve full combat
    (no HP/damage) — it only decides whether a single physical/skill-based attempt
    succeeds, so the narrator has a true mechanical fact to describe. Full combat
    simulation is out of scope for the MVP (see spec section 58)."""
    cskill = grant_skill(db, character_id, skill_name)
    mastery_modifier = int(cskill.mastery // 10)
    relevant_attribute_modifier = 0
    if attribute_key is not None:
        attribute = get_character_attribute(db, character_id, attribute_key)
        relevant_attribute_modifier = attribute_check_modifier(attribute.value)
    modifier = mastery_modifier + relevant_attribute_modifier

    result = dice.d20(modifier=modifier)
    critical = result.raw == 20
    success = critical or (result.raw != 1 and result.total >= dc)

    return SkillCheckResult(
        skill_name=skill_name,
        dc=dc,
        roll=result,
        success=success,
        critical=critical,
        attribute_key=attribute_key.value if attribute_key is not None else None,
        attribute_modifier=relevant_attribute_modifier,
    )
