"""Phase 12F — Rewards.

Distinguishes PROMISED reward (what was said — narrative only, no
system-backed materialization) from ACTUAL reward (what a real backend
system can actually grant). Inventory and progression are integrated
here; other reward kinds must still be routed explicitly through their
own authoritative systems rather than invented from narrative text.

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

from app.ai.llm_service import LLMService
from app.core.enums import CharacterXPSource, CombatActorType, ItemQuality
from app.db.models.character import Character
from app.db.models.item import ItemInstance
from app.db.models.organization import Organization
from app.db.models.quest import CharacterQuest, Quest
from app.game.inventory.service import add_item
from app.game.organizations.reputation import award_organization_reputation
from app.game.progression.outcomes import (
    CharacterXPGain,
    ProgressionOutcome,
    resolve_progression_outcome,
)


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


def grant_pending_quest_completion_xp(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    character: Character,
) -> list[tuple[str, float]]:
    """Apply each newly completed quest reward exactly once.

    CharacterQuest.reward_granted records delivery while ProgressionOutcome's
    outcome key provides a second idempotency boundary if a transaction is
    retried between applying XP and marking the participation.
    """
    pending = (
        db.query(CharacterQuest, Quest)
        .join(Quest, Quest.id == CharacterQuest.quest_id)
        .filter(
            CharacterQuest.character_id == character.id,
            CharacterQuest.status == "COMPLETED",
            CharacterQuest.reward_granted.is_(False),
        )
        .all()
    )
    granted: list[tuple[str, float]] = []
    for participation, quest in pending:
        amount = max(0.0, float(quest.xp_reward or 0.0))
        if amount:
            outcome = quest_completion_progression_outcome(
                quest,
                outcome_key=f"quest-completed:{quest.id}",
                xp_amount=amount,
            )
            resolve_progression_outcome(
                db,
                llm_service,
                campaign_id,
                character,
                outcome,
            )
            granted.append((quest.name, amount))
        if quest.sponsoring_organization_id:
            organization = db.get(Organization, quest.sponsoring_organization_id)
            if organization is not None:
                # A contract completed directly for its sponsor is its own
                # witness (Phase 13G).  The small relevance-scaled change
                # makes both initial contracts together establish a RELIABLE
                # reputation without letting one trivial task do so alone.
                reputation_delta = max(1, min(10, round(amount / 5)))
                award_organization_reputation(
                    db,
                    organization,
                    CombatActorType.CHARACTER,
                    character.id,
                    delta=reputation_delta,
                    reason=f"Concluiu o contrato '{quest.name}'.",
                )
        participation.reward_granted = True
    if pending:
        db.flush()
    return granted
