from app.ai.context_builder import fact_is_revealed_in_text
from app.ai.llm_service import LLMService
from app.api.serializers import to_game_state_response
from app.core.enums import DiscoveryStatus, KnowerType
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.game import engine
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.game_state import build_game_state
from app.game.npcs.service import KnownFact
from app.game.world.seed import create_campaign, grant_initial_player_knowledge, seed_initial_region


def _cardal_scene(db_session):
    campaign = create_campaign(db_session, "Dialogue Knowledge")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    grant_initial_player_knowledge(db_session, campaign.id, character.id)
    db_session.commit()
    return campaign, character


class NarratingLLM(LLMService):
    """Simulates a real narrator: correctly classifies TALK, then has the NPC
    voice a known fact in paraphrased, in-character dialogue."""

    def __init__(self, narration: str) -> None:
        self.calls: list[tuple[str, str]] = []
        self._narration = narration

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            return '{"intent": "TALK", "target": "Osgar Vell"}'
        return self._narration


def _player_fact_keys(db_session, character_id: str) -> set[str]:
    rows = (
        db_session.query(KnowledgeFact.fact_key)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character_id,
        )
        .all()
    )
    return {row[0] for row in rows}


def test_npc_revealing_the_village_name_in_dialogue_teaches_the_player(db_session):
    campaign, character = _cardal_scene(db_session)

    state = build_game_state(db_session, campaign.id, character.id)
    assert to_game_state_response(db_session, state).location.name is None

    llm = NarratingLLM("— Isto aqui é Cardal, uma vila tranquila do Vale Verdejante.")
    engine.resolve_action(
        db_session, llm, campaign.id, character.id,
        "— Com licença, como se chama este lugar?",
    )

    # No extra LLM call: still just intent-parse + narration.
    assert len(llm.calls) == 2
    assert "cardal_is_village" in _player_fact_keys(db_session, character.id)

    state_after = build_game_state(db_session, campaign.id, character.id)
    response_after = to_game_state_response(db_session, state_after)
    assert response_after.location.name == "Cardal"
    assert response_after.region.name == "Vale Verdejante"


def test_npc_not_mentioning_the_name_does_not_teach_it(db_session):
    campaign, character = _cardal_scene(db_session)

    llm = NarratingLLM("— Bom dia. Em que posso ajudar?")
    engine.resolve_action(
        db_session, llm, campaign.id, character.id, "— Bom dia.",
    )

    assert "cardal_is_village" not in _player_fact_keys(db_session, character.id)

    state_after = build_game_state(db_session, campaign.id, character.id)
    assert to_game_state_response(db_session, state_after).location.name is None


def test_repeated_reveals_across_turns_stay_idempotent(db_session):
    campaign, character = _cardal_scene(db_session)

    llm = NarratingLLM("— Isto aqui é Cardal, uma vila tranquila do Vale Verdejante.")
    engine.resolve_action(
        db_session, llm, campaign.id, character.id, "— Onde estou?",
    )
    engine.resolve_action(
        db_session, llm, campaign.id, character.id, "— E qual o nome deste lugar mesmo?",
    )

    keys = [
        row[0]
        for row in db_session.query(KnowledgeKnower.id)
        .join(KnowledgeFact, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character.id,
            KnowledgeFact.fact_key == "cardal_is_village",
        )
        .all()
    ]
    assert len(keys) == 1


def test_fact_is_revealed_in_text_matches_a_paraphrased_reveal():
    fact = KnownFact(
        subject="location:village_1",
        fact_key="cardal_is_village",
        statement="Cardal é uma vila da região Vale Verdejante.",
        source="experiência local",
        certainty="CONFIRMED",
        discovered_at=None,
    )

    assert fact_is_revealed_in_text(
        fact, "— Isto aqui é Cardal, uma vila tranquila do Vale Verdejante.",
    )


def test_fact_is_revealed_in_text_rejects_a_missing_named_entity():
    fact = KnownFact(
        subject="location:village_1",
        fact_key="cardal_is_village",
        statement="Cardal é uma vila da região Vale Verdejante.",
        source="experiência local",
        certainty="CONFIRMED",
        discovered_at=None,
    )

    # Only one of the two names ("Cardal") was actually said.
    assert not fact_is_revealed_in_text(
        fact, "— Isto aqui é Cardal, uma vila tranquila.",
    )
