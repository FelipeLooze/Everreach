from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.game import dice
from app.game.skills.service import grant_skill

DEFAULT_DC = 12


@dataclass
class SkillCheckResult:
    skill_name: str
    dc: int
    roll: dice.RollResult
    success: bool
    critical: bool


def resolve_skill_check(
    db: Session, character_id: str, skill_name: str, dc: int = DEFAULT_DC
) -> SkillCheckResult:
    """Generic d20 + mastery check. This intentionally does NOT resolve full combat
    (no HP/damage) — it only decides whether a single physical/skill-based attempt
    succeeds, so the narrator has a true mechanical fact to describe. Full combat
    simulation is out of scope for the MVP (see spec section 58)."""
    cskill = grant_skill(db, character_id, skill_name)
    modifier = int(cskill.mastery // 10)

    result = dice.d20(modifier=modifier)
    critical = result.raw == 20
    success = critical or (result.raw != 1 and result.total >= dc)

    return SkillCheckResult(skill_name=skill_name, dc=dc, roll=result, success=success, critical=critical)
