from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger("narration")


@dataclass
class ValidationResult:
    text: str
    warnings: list[str]


def validate(text: str, canonical_facts: dict) -> ValidationResult:
    """Lightweight anti-hallucination checks against known canonical facts.

    This is intentionally minimal for the MVP: simple keyword checks, not semantic
    understanding. It flags likely contradictions (e.g. narrating a dead NPC as
    present) rather than trying to rewrite the text automatically. Full narrative
    validation (semantic contradiction detection) is future work — not silently
    pretended to be solved here.
    """
    warnings: list[str] = []

    if not canonical_facts.get("character_alive", True):
        warnings.append("Character is dead but a new action was narrated.")

    for dead_name in canonical_facts.get("dead_npc_names", []):
        if dead_name and dead_name in text:
            warnings.append(f"Narrator mentioned '{dead_name}', who is recorded as dead.")

    if warnings:
        logger.warning("narrative validation warnings: %s", warnings)

    return ValidationResult(text=text, warnings=warnings)
