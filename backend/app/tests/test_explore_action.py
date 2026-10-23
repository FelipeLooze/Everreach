"""Active exploration is a real action now (2026-10-23): "exploro a região"
searches nearby for an unknown route, the world clock advances through the
engine, and the find is told as the player can know it."""
import json

from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import ActionIntentType
from app.db.models.location import CharacterConnectionDiscovery
from app.game import engine
from app.game.character.service import create_character
from app.game.exploration import service as exploration
from app.game.time.clock import get_world_time
from app.game.world.seed import create_campaign, seed_initial_region


class _Explorer(LLMService):
    def generate(self, system, prompt):
        if "Ação do jogador" in prompt:
            return json.dumps({"intent": "FREEFORM", "target": None})
        return "A busca segue."


def _world(db_session):
    campaign = create_campaign(db_session, "Exploração")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.flush()
    return campaign, character


def test_exploring_phrases_become_the_explore_action_and_looking_does_not():
    def refined(text):
        return engine._refine_explicit_membership_intent(
            Intent(type=ActionIntentType.FREEFORM, target=None, raw_text=text)
        ).type

    for text in ("Exploro os arredores", "Vou vasculhar a área", "Procuro outras trilhas por aqui",
                 "Quero descobrir a região"):
        assert refined(text) == ActionIntentType.EXPLORE, text
    assert refined("Olho ao redor com calma") == ActionIntentType.FREEFORM


def test_exploring_finds_a_route_spends_world_time_and_never_names_the_place(db_session, monkeypatch):
    campaign, character = _world(db_session)
    monkeypatch.setattr(exploration, "d20", lambda rng=None: type("Roll", (), {"total": 20})())
    known_before = db_session.query(CharacterConnectionDiscovery).filter_by(character_id=character.id).count()
    before = get_world_time(db_session, campaign.id).total_minutes()
    llm = _Explorer()

    result = engine.resolve_action(db_session, llm, campaign.id, character.id, "Exploro os arredores",
                                   intent_llm_service=llm)

    assert result.intent_type == ActionIntentType.EXPLORE.value
    assert "explora os arredores por 1h30 e encontra uma" in result.mechanical_summary
    assert "ainda desconhecido" in result.mechanical_summary
    assert db_session.query(CharacterConnectionDiscovery).filter_by(character_id=character.id).count() == known_before + 1
    assert get_world_time(db_session, campaign.id).total_minutes() - before >= exploration.EXPLORATION_MINUTES


def test_a_failed_search_still_takes_the_time(db_session, monkeypatch):
    campaign, character = _world(db_session)
    monkeypatch.setattr(exploration, "d20", lambda rng=None: type("Roll", (), {"total": 1})())
    llm = _Explorer()

    result = engine.resolve_action(db_session, llm, campaign.id, character.id, "Vasculho a área",
                                   intent_llm_service=llm)

    assert "não encontra nenhum caminho novo" in result.mechanical_summary


def test_a_place_found_by_exploring_shows_on_the_map_without_its_name(db_session, monkeypatch):
    from app.game.map.view import get_map_view

    campaign, character = _world(db_session)
    monkeypatch.setattr(exploration, "d20", lambda rng=None: type("Roll", (), {"total": 20})())

    outcome = exploration.explore_current_location(db_session, campaign.id, character)

    found = next(row for row in get_map_view(db_session, campaign.id, character.id).locations
                 if row.id == outcome.found_location_id)
    assert found.discovery_status == "DISCOVERED" and found.name is None
