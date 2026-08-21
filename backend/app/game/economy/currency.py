"""Phase 14A — Currency Foundation.

Pure denomination math — no database access. Bronze is the canonical
smallest unit everywhere else in the economy system (CurrencyHolding,
Organization.treasury): 100 Bronze = 1 Silver, 100 Silver = 1 Gold, fixed
per the spec, integer arithmetic only — there is no fractional Bronze,
so no floating-point value ever represents money in this codebase.

Gold must stay rare and meaningful (the spec's core economic
philosophy) — nothing in this module enforces that by itself; it is a
content/design discipline for whoever sets prices/wages/rewards later
(Phase 14B+), not a mechanical constraint this conversion math could
express.
"""

BRONZE_PER_SILVER = 100
SILVER_PER_GOLD = 100
BRONZE_PER_GOLD = BRONZE_PER_SILVER * SILVER_PER_GOLD


class CurrencyError(ValueError):
    pass


class CurrencyDenomination:
    """A read-only Gold/Silver/Bronze breakdown of an amount, purely for
    display — the canonical value is always the underlying amount_bronze
    integer, never this breakdown."""

    __slots__ = ("gold", "silver", "bronze")

    def __init__(self, gold: int, silver: int, bronze: int) -> None:
        self.gold = gold
        self.silver = silver
        self.bronze = bronze

    def __repr__(self) -> str:
        return f"CurrencyDenomination(gold={self.gold}, silver={self.silver}, bronze={self.bronze})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CurrencyDenomination):
            return NotImplemented
        return (self.gold, self.silver, self.bronze) == (other.gold, other.silver, other.bronze)


def to_denominations(amount_bronze: int) -> CurrencyDenomination:
    """25,430 Bronze -> 2 Gold, 54 Silver, 30 Bronze."""
    if not isinstance(amount_bronze, int) or isinstance(amount_bronze, bool):
        raise CurrencyError("Valores de moeda precisam ser inteiros (Bronze é a menor unidade).")
    if amount_bronze < 0:
        raise CurrencyError("Valores negativos de moeda não são permitidos.")
    gold, remainder = divmod(amount_bronze, BRONZE_PER_GOLD)
    silver, bronze = divmod(remainder, BRONZE_PER_SILVER)
    return CurrencyDenomination(gold=gold, silver=silver, bronze=bronze)


def from_denominations(*, gold: int = 0, silver: int = 0, bronze: int = 0) -> int:
    """The inverse of to_denominations — collapses a Gold/Silver/Bronze
    breakdown back into the canonical smallest-unit amount."""
    for label, value in (("gold", gold), ("silver", silver), ("bronze", bronze)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise CurrencyError(f"O valor de {label} precisa ser um inteiro.")
        if value < 0:
            raise CurrencyError(f"O valor de {label} não pode ser negativo.")
    return gold * BRONZE_PER_GOLD + silver * BRONZE_PER_SILVER + bronze
