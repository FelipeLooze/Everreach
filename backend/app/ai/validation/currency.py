"""Phase 19J — Item / Equipment / Currency Validator.

Reuses app.game.economy.wallet.total_carried_by_owner and
app.game.economy.currency.from_denominations (Phase 14) rather than a
parallel currency-tracking mechanism — the spec's own worked example
("Mira places twenty Silver on the counter... if authoritative funds do
not support it: reject") is a direct currency check, so that's this
subphase's scope. Full item/equipment claim matching (mapping an
arbitrary narrated weapon noun to a specific ItemDefinition category in
the character's inventory) needs a curated narrative-noun vocabulary
this subphase does not build — deferred, documented, not silently
skipped.

Deliberately conservative: only digit or small curated word-number
quantities are recognized; an amount phrased outside that vocabulary is
never flagged (under-detection over false rejection, per the Phase 19G
lesson).
"""
import re

from sqlalchemy.orm import Session

from app.ai.narrator import _normalized
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.core.enums import CombatActorType
from app.game.economy.currency import from_denominations
from app.game.economy.wallet import total_carried_by_owner

_WORD_NUMBERS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12,
    "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "cem": 100,
}
_WORD_NUMBER_PATTERN = "|".join(_WORD_NUMBERS)

_DENOMINATION_KEYS = {
    "ouro": "gold", "prata": "silver", "pratas": "silver", "bronze": "bronze",
}

_PAYMENT_CLAIM = re.compile(
    rf"\b(\d+|{_WORD_NUMBER_PATTERN})\s+(?:moedas?\s+de\s+)?"
    rf"(ouro|pratas?|bronze)\b",
    re.IGNORECASE,
)


def _parse_quantity(token: str) -> int:
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS[token]


def _claimed_bronze_amount(text: str) -> int | None:
    match = _PAYMENT_CLAIM.search(_normalized(text))
    if not match:
        return None
    quantity = _parse_quantity(match.group(1))
    denomination = _DENOMINATION_KEYS[match.group(2).lower()]
    return from_denominations(**{denomination: quantity})


@register_validator
def validate_currency(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    if not proposal.character_id:
        return []

    violations = []
    for claim in claims:
        claimed_bronze = _claimed_bronze_amount(claim.text)
        if claimed_bronze is None:
            continue
        available = total_carried_by_owner(db, CombatActorType.CHARACTER, proposal.character_id)
        if claimed_bronze > available:
            violations.append(
                Violation(
                    claim_index=claim.index,
                    category=ClaimCategory.AUTHORITATIVE,
                    reason=(
                        f"'{claim.text}' menciona uma quantia de moedas que excede o que o "
                        f"personagem realmente carrega."
                    ),
                )
            )
    return violations
