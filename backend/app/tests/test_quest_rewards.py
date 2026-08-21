"""Phase 12F — Rewards.

grant_quest_item_rewards only ever materializes the actual (item) side of
an offer, through the real Inventory system — promised rewards
(currency/services/access/...) are narrative-only until Phase 14 gives
them a system to land in. quest_completion_progression_outcome builds,
but never applies, a ProgressionOutcome — same "emit outcome, let
Progression decide" convention as Phase 11 techniques.
"""

from app.ai.llm_service import LLMService
from app.core.enums import ItemQuality, QuestSource
from app.game.character.service import create_character
from app.game.inventory.service import list_inventory
from app.game.progression.outcomes import resolve_progression_outcome
from app.game.quests.rewards import (
    ItemReward,
    PromisedReward,
    QuestRewardOffer,
    grant_quest_item_rewards,
    quest_completion_progression_outcome,
)
from app.game.quests.service import create_quest
from app.game.world.seed import create_campaign, seed_initial_region


class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "A ação acontece conforme o resultado mecânico."


def _setup(db_session):
    campaign = create_campaign(db_session, "Quest Rewards")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, character


def test_grant_quest_item_rewards_materializes_only_the_item_side(db_session):
    campaign, region, character = _setup(db_session)
    offer = QuestRewardOffer(
        promised=(PromisedReward(description="20 moedas de prata, segundo Darven."),),
        items=(ItemReward(item_name="Ração de Viagem", quantity=3, quality=ItemQuality.STANDARD),),
    )

    granted = grant_quest_item_rewards(db_session, character.id, offer)

    assert len(granted) == 1
    assert granted[0].definition.name == "Ração de Viagem"
    inventory = list_inventory(db_session, character.id)
    assert any(entry.definition.name == "Ração de Viagem" and entry.quantity == 3 for entry in inventory)


def test_promised_reward_alone_grants_nothing(db_session):
    campaign, region, character = _setup(db_session)
    offer = QuestRewardOffer(promised=(PromisedReward(description="Acesso à guilda dos ferreiros."),))

    granted = grant_quest_item_rewards(db_session, character.id, offer)

    assert granted == []
    assert list_inventory(db_session, character.id) == []


def test_quest_completion_progression_outcome_grants_character_xp_through_the_real_system(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)
    starting_xp = character.xp

    outcome = quest_completion_progression_outcome(
        quest, outcome_key=f"quest-completed:{quest.id}", xp_amount=12.0
    )
    resolve_progression_outcome(db_session, PassiveLLM(), campaign.id, character, outcome)

    assert character.xp == starting_xp + 12.0


def test_quest_completion_progression_outcome_is_idempotent_per_outcome_key(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)

    outcome = quest_completion_progression_outcome(
        quest, outcome_key=f"quest-completed:{quest.id}", xp_amount=12.0
    )
    resolve_progression_outcome(db_session, PassiveLLM(), campaign.id, character, outcome)
    xp_after_first = character.xp
    resolve_progression_outcome(db_session, PassiveLLM(), campaign.id, character, outcome)

    assert character.xp == xp_after_first
