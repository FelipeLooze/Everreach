"""The animals around the starting village (2026-10-24): common fauna near
it; only far out, deep in the woods, something uncommon (added separately).

A creature is an NPC row with ``creature_species`` set, so the combat engine
fights it unchanged. Species differ in where and when they are found, how
tough they are and whether they attack on sight.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Species:
    key: str
    singular: str  # "lobo"
    plural: str  # "lobos"
    feminine: bool
    # Location type -> how many live there at most.
    habitats: dict[str, int]
    # Hours (start, end) when they are out and can be met; may wrap midnight.
    active: tuple[tuple[int, int], ...]
    hp: float
    # 0-100; at or above combat.hostility.HOSTILE_THRESHOLD they attack on sight.
    hostility: int
    # How the narrator should play them when met.
    behavior: str
    # Distinguishing looks, so two wolves are never the same "Lobo".
    marks: tuple[str, ...]
    # For the portrait prompt (the visual identity reads English).
    english: str = "animal"


SPECIES = {
    species.key: species
    for species in (
        Species(
            "wolf", "lobo", "lobos", False, {"forest": 2, "clearing": 3}, ((19, 24), (0, 6)), 9, 85,
            "hunts in a pack at night and attacks on sight; flees when badly hurt",
            ("cinzento", "de orelha rasgada", "de pelo escuro", "magro", "de focinho branco", "manco"),
            "a wild grey wolf",
        ),
        Species(
            "boar", "javali", "javalis", False, {"forest": 2, "clearing": 1, "plains": 2}, ((6, 18),), 12, 30,
            "roots around by day; ignores people unless cornered or attacked, then charges hard",
            ("de presas longas", "malhado", "de cerdas eriçadas", "jovem", "enorme"),
            "a wild boar",
        ),
        Species(
            "deer", "cervo", "cervos", False, {"clearing": 2, "forest": 1, "river": 2}, ((5, 9), (16, 20)), 8, 0,
            "grazes at dawn and dusk and bolts at the first noise; never attacks",
            ("de galhada larga", "jovem", "de pelo avermelhado", "de pescoço longo"),
            "a red deer",
        ),
        Species(
            "fox", "raposa", "raposas", True, {"road": 1, "forest": 1, "river": 1}, ((17, 24), (0, 7)), 4, 0,
            "slinks along the edges at night, curious but wary; never attacks",
            ("ruiva", "de cauda espessa", "de patas pretas", "esguia"),
            "a red fox",
        ),
    )
}


def is_active(species: Species, hour: int) -> bool:
    return any(start <= hour < end for start, end in species.active)
