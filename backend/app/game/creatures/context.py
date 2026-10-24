"""How the animals out at a place reach the narrator and the intent parser."""

from collections import Counter

from app.game.creatures.species import get


def creature_lines(state) -> list[str]:
    creatures = list(getattr(state, "nearby_creatures", []))
    if not creatures:
        return []
    lines = ["VISIBLE CREATURES"]
    counts = Counter(creature.creature_species for creature in creatures)
    for key, count in counts.items():
        species = get(key)
        if species is None:
            continue
        names = ", ".join(creature.name for creature in creatures if creature.creature_species == key)
        word = species.singular if count == 1 else species.plural
        behavior = f" — {species.behavior}" if species.behavior else ""
        lines.append(f"- {count} {word.casefold()} ({names}){behavior}")
    lines.append(
        "These animals are exactly what is here: never add others, and never let them speak. "
        "Describe them by look, sound, smell and movement; never reveal stats, weaknesses or loot. "
        "A fight starts only from the mechanics (an attack or an ambush), never from the narration."
    )
    return lines
