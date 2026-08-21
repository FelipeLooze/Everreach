"""Phase 12F — Rewards.

Distinguishes PROMISED reward (what was said — narrative only, no
system-backed materialization) from ACTUAL reward (what a real backend
system, today only Inventory, can actually grant). Currency, services,
access, training, employment, lodging, favors and contracts have no
backing system yet (Phase 14 Economy) — a PromisedReward for those stays
descriptive text; nothing here invents currency out of thin air.

Character XP is not owned here either: quest completion emits a
ProgressionOutcome (mirroring Phase 11's technique_progression_outcome)
for the caller to apply through resolve_progression_outcome — the amount
is supplied by the caller, since there is no quest difficulty-scoring
system to derive it from automatically. Profession XP, Domain Evidence,
Attribute growth and Technique evidence are likewise never granted
directly by quest completion; only the actual actions that occurred
during the quest would populate those, through their own systems.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import CharacterXPSource, ItemQuality
from app.db.models.item import ItemInstance
from app.db.models.quest import Quest
from app.game.inventory.service import add_item
from app.game.progression.outcomes import CharacterXPGain, ProgressionOutcome


@dataclass(frozen=True)
class PromisedReward:
    """What was said — narrative only. Nothing here materializes it; see
    the Phase 12 spec's PROMISED REWARD VS ACTUAL REWARD distinction."""

    description: str


@dataclass(frozen=True)
class ItemReward:
    """An actual reward the backend can materialize today, through the
    real Inventory system (Phase 10)."""

    item_name: str
    quantity: int = 1
    quality: ItemQuality = ItemQuality.STANDARD


@dataclass(frozen=True)
class QuestRewardOffer:
    promised: tuple[PromisedReward, ...] = ()
    items: tuple[ItemReward, ...] = ()


def grant_quest_item_rewards(
    db: Session, character_id: str, offer: QuestRewardOffer
) -> list[ItemInstance]:
    """Materializes only the actual (item) side of a reward offer.
    Promised rewards are never auto-granted — what actually happens to a
    promise (paid, negotiated, refused, the payer died...) is a world/
    narrative outcome outside this function's authority."""
    return [
        add_item(db, character_id, item.item_name, item.quantity, quality=item.quality)
        for item in offer.items
    ]


def quest_completion_progression_outcome(
    quest: Quest, *, outcome_key: str, xp_amount: float
) -> ProgressionOutcome:
    """Builds — never applies — the ProgressionOutcome for a quest
    accomplishment. The caller applies it via
    app.game.progression.outcomes.resolve_progression_outcome, exactly
    like Phase 11's technique_progression_outcome."""
    return ProgressionOutcome(
        outcome_key=outcome_key,
        character_xp=CharacterXPGain(amount=xp_amount, source=CharacterXPSource.IMPORTANT_OBJECTIVE),
    )
