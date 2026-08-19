from app.ai.llm_service import LLMService
from app.core.enums import (
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
    SimulatedPlayerStatus,
)
from app.db.models.simulated_player import SimulatedPlayer
from app.game.players.generator import materialize_simulated_player
from app.game.world.seed import create_campaign, seed_initial_region


class IdentityLLM(LLMService):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(
        self,
        system: str,
        prompt: str,
    ) -> str:
        self.calls.append(
            (system, prompt)
        )

        return """
        {
        "name": "Kaelen Voss",
        "personality": "Curioso, cauteloso e observador.",
        "background": "Trabalhava como técnico de manutenção antes da Chegada.",
        "motivation": "Encontrar alguma estabilidade neste novo mundo.",
        "goal": "Encontrar outras pessoas transportadas e descobrir o que aconteceu.",
        "physical_description": "Homem jovem de pele morena clara, cabelo preto curto e ondulado, olhos castanhos, porte magro e barba curta.",
        "archetype": "SOCIAL"
        }
        """


def test_materialize_simulated_player_persists_llm_identity(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Materialization Test",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    llm = IdentityLLM()

    created = materialize_simulated_player(
        db_session,
        llm,
        campaign.id,
        location.id,
    )

    persisted = db_session.get(
        SimulatedPlayer,
        created.id,
    )

    assert persisted is not None

    assert persisted.campaign_id == campaign.id
    assert persisted.location_id == location.id

    assert persisted.name == "Kaelen Voss"

    assert (
        persisted.personality
        == "Curioso, cauteloso e observador."
    )

    assert (
        persisted.background
        == "Trabalhava como técnico de manutenção antes da Chegada."
    )

    assert (
        persisted.motivation
        == "Encontrar alguma estabilidade neste novo mundo."
    )

    assert (
        persisted.physical_description
        == "Homem jovem de pele morena clara, cabelo preto curto e ondulado, olhos castanhos, porte magro e barba curta."
    )

    assert (
        persisted.goal
        == "Encontrar outras pessoas transportadas e descobrir o que aconteceu."
    )

    assert (
        persisted.archetype
        == SimulatedPlayerArchetype.SOCIAL
    )

    assert (
        persisted.goal_type
        == SimulatedPlayerGoalType.NONE
    )

    assert persisted.goal_subject is None

    assert persisted.level == 0

    assert (
        persisted.status
        == SimulatedPlayerStatus.ACTIVE
    )

    assert len(llm.calls) == 1
    assert location.name in llm.calls[0][1]