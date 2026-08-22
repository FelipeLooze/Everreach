from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.ai import context_builder, narrator
from app.ai.llm_service import LLMService
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.quest import Quest, QuestObjective
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.quests.service import start_quest
from app.game.world.seed import create_campaign, seed_initial_region


class RecordingLLM(LLMService):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return "Narração controlada."


def test_context_builder_sends_only_current_player_context(db_session):
    campaign = create_campaign(db_session, "Context Test")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)

    elder = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.role == "ancião da vila").one()
    # Scoped to the anchor subregion, not the whole region: "forest" as a
    # Location.type also occurs elsewhere in the massive region (any other
    # FOREST-biome subregion's own generic geography feature).
    forest = db_session.query(Location).filter(
        Location.subregion_id == village.subregion_id, Location.type == "forest"
    ).one()
    clearing = db_session.query(Location).filter(Location.region_id == region.id, Location.type == "clearing").one()
    blacksmith = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.role == "ferreira").one()

    quest = Quest(
        region_id=region.id,
        name="Quest de Teste",
        description="Quest criada exclusivamente para o teste.",
    )
    db_session.add(quest)
    db_session.flush()

    objective = QuestObjective(
        quest_id=quest.id,
        description=f"Falar com {elder.name} em {village.name}.",
        order=0,
    )
    db_session.add(objective)
    db_session.flush()

    start_quest(db_session, character.id, quest.id)

    db_session.commit()

    context = context_builder.build_context(
        db_session, build_game_state(db_session, campaign.id, character.id)
    )

    assert region.name in context
    assert village.name in context
    assert "Hero" in context
    assert elder.name in context
    assert forest.name not in context
    assert clearing.name not in context
    assert blacksmith.backstory not in context
    assert "NPCs do not know it automatically" in context
    assert "main_boss" not in context
    assert "WORLD_STARTED" not in context
def test_only_llm_service_contains_ollama_transport_code():
    app_root = Path(__file__).parents[1]
    transport_owner = app_root / "ai" / "llm_service.py"

    for source_path in app_root.rglob("*.py"):
        if "tests" in source_path.parts or source_path == transport_owner:
            continue
        source = source_path.read_text(encoding="utf-8")
        assert "import httpx" not in source
        assert "/api/generate" not in source


def test_narrator_only_delegates_text_generation_to_llm_service():
    llm = RecordingLLM()

    result = narrator.narrate(
        llm,
        "O personagem chegou a Cardal.",
        "Local: Cardal",
        player_input="Olho ao meu redor.",
        recent_history="NARRATOR: A praça está movimentada.",
    )

    assert result == "Narração controlada."
    assert len(llm.calls) == 1
    _system, prompt = llm.calls[0]
    assert "O personagem chegou a Cardal." in prompt
    assert "Local: Cardal" in prompt
    assert "Olho ao meu redor." in prompt
    assert "A praça está movimentada." in prompt
    narrator_source = Path(narrator.__file__).read_text(encoding="utf-8")
    assert "sqlalchemy" not in narrator_source
    assert "app.db" not in narrator_source


def test_sqlite_foreign_keys_are_enforced_in_tests(db_session):
    db_session.add(Character(campaign_id="campaign_inexistente", name="Sem campanha"))

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_api_rejects_character_from_another_campaign(client, fake_llm):
    first = client.post("/api/campaigns", json={"name": "Primeira"}).json()
    second = client.post("/api/campaigns", json={"name": "Segunda"}).json()
    character = client.post(
        f"/api/campaigns/{first['id']}/characters", json={"name": "Hero"}
    ).json()

    routes = (
        f"/api/campaigns/{second['id']}/state",
        f"/api/campaigns/{second['id']}/inventory",
        f"/api/campaigns/{second['id']}/quests",
        f"/api/campaigns/{second['id']}/character",
        f"/api/campaigns/{second['id']}/story",
    )
    for route in routes:
        response = client.get(route, params={"character_id": character["id"]})
        assert response.status_code == 404

    response = client.post(
        f"/api/campaigns/{second['id']}/actions",
        params={"character_id": character["id"]},
        json={"text": "Espero."},
    )
    assert response.status_code == 404
    assert fake_llm.calls == []


    @pytest.mark.parametrize(
        ("resource", "params"),
        [
            ("map", {"character_id": "char_inexistente"}),
            ("journal", None),
        ],
    )
    def test_campaign_resources_return_404_for_unknown_campaign(
        client,
        resource,
        params,
    ):
        response = client.get(
            f"/api/campaigns/campaign_inexistente/{resource}",
            params=params,
        )

        assert response.status_code == 404


@pytest.mark.parametrize("endpoint", ["/api/campaigns", "/api/campaigns/campaign_id/characters"])
def test_campaign_and_character_names_cannot_be_blank(client, endpoint):
    response = client.post(endpoint, json={"name": "   "})
    assert response.status_code == 422


def test_action_text_cannot_be_blank(client):
    response = client.post(
        "/api/campaigns/campaign_id/actions",
        params={"character_id": "character_id"},
        json={"text": "   "},
    )
    assert response.status_code == 422
