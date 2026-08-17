from app.db.models.character import Character


def xp_to_next_level(level: int) -> float:
    """XP required to go from `level` to `level + 1`. Grows progressively — no fixed cap."""
    return round(50 * (level + 1) ** 1.5, 1)


def add_xp(character: Character, amount: float) -> int:
    """Add XP to a character, applying level-ups. Returns the number of levels gained."""
    if amount <= 0:
        return 0

    character.xp += amount
    levels_gained = 0

    while character.xp >= xp_to_next_level(character.level):
        character.xp -= xp_to_next_level(character.level)
        character.level += 1
        levels_gained += 1

    return levels_gained
