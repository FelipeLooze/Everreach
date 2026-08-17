import random
from dataclasses import dataclass


@dataclass
class RollResult:
    sides: int
    raw: int
    modifier: int

    @property
    def total(self) -> int:
        return self.raw + self.modifier


def roll(sides: int, modifier: int = 0, rng: random.Random | None = None) -> RollResult:
    """Roll a single die. The Game Engine is the only place dice are rolled — never the LLM."""
    r = rng or random
    raw = r.randint(1, sides)
    return RollResult(sides=sides, raw=raw, modifier=modifier)


def d20(modifier: int = 0, rng: random.Random | None = None) -> RollResult:
    return roll(20, modifier, rng)
