import pytest
from app.ai.llm_service import LLMService
from app.core.enums import (
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
    SimulatedPlayerStatus,
)
from app.db.models.simulated_player import SimulatedPlayer
from app.game.players.generator import materialize_simulated_player
from app.game.world.seed import create_campaign, seed_initial_region
from app.game.players.service import (
    abstract_simulated_player_count_at_location,
    set_abstract_simulated_player_population,
)

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


class ProfessionalIdentityLLM(LLMService):
    def __init__(self, background: str, earth_profession: str) -> None:
        self.background = background
        self.earth_profession = earth_profession

    def generate(self, system: str, prompt: str) -> str:
        return f"""
        {{
          "name": "Marina Costa",
          "personality": "Prática e paciente.",
          "background": "{self.background}",
          "earth_profession": "{self.earth_profession}",
          "motivation": "Encontrar trabalho seguro.",
          "goal": "Conseguir abrigo.",
          "physical_description": "Mulher adulta de cabelos castanhos e olhos escuros.",
          "archetype": "SOCIAL"
        }}
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

    set_abstract_simulated_player_population(
        db_session,
        campaign.id,
        location.id,
        1,
    )

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

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 0
    )

    calls_before_second_attempt = len(llm.calls)

    with pytest.raises(
        ValueError,
        match="No abstract simulated player population",
    ):
        materialize_simulated_player(
            db_session,
            llm,
            campaign.id,
            location.id,
        )

    assert len(llm.calls) == calls_before_second_attempt


@pytest.mark.parametrize(
    ("background", "declared_profession", "expected_affinity"),
    [
        ("Era chef profissional na Terra.", "CHEF", "CULINARY"),
        (
            "Trabalhava como engenheira de software na Terra.",
            "BLACKSMITH",
            None,
        ),
    ],
)
def test_materialization_only_accepts_matching_background_affinity(
    db_session,
    background,
    declared_profession,
    expected_affinity,
):
    campaign = create_campaign(db_session, "Generated Affinity")
    _region, location = seed_initial_region(db_session, campaign.id)
    set_abstract_simulated_player_population(
        db_session,
        campaign.id,
        location.id,
        1,
    )

    player = materialize_simulated_player(
        db_session,
        ProfessionalIdentityLLM(background, declared_profession),
        campaign.id,
        location.id,
    )

    assert player.profession_affinity_key == expected_affinity
