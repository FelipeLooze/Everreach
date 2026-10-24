"""The player refers to people by what the narrator described; the engine
resolves the same description (2026-10-23, the user's own save)."""
import json

from app.ai.llm_service import LLMService
from app.ai.people_present import (
    build_intent_context,
    npc_appearance_pt,
    people_present_lines,
    person_for_ref,
    present_people,
)
from app.game import engine
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.players.appearance import ensure_transported_features
from app.game.world.seed import create_campaign, seed_initial_region


def _world(db_session):
    campaign = create_campaign(db_session, "Pessoas")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.flush()
    return campaign, character


class _Parser(LLMService):
    """Intent calls answer with the given person; narration counts calls."""

    def __init__(self, person):
        self.person = person
        self.narrations = 0

    def generate(self, system, prompt):
        if "Ação do jogador" in prompt:
            return json.dumps({"intent": "TALK", "target": None, "person": self.person})
        self.narrations += 1
        return "A cena segue."


def test_everyone_present_has_a_registered_look(db_session):
    campaign, character = _world(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    elder = next(npc for npc in state.nearby_npcs if npc.role == "ancião da vila")

    looks = npc_appearance_pt(db_session, campaign.id, elder)
    assert looks.startswith("homem idoso, ") and "cabelo branco" in looks and " usa " in looks
    assert npc_appearance_pt(db_session, campaign.id, elder, short=True).startswith("homem idoso, cabelo branco")
    stranger = state.nearby_simulated_players[0]
    first = ensure_transported_features(db_session, stranger)
    assert first.startswith(("Homem", "Mulher")) and "cabelo" in first and "olhos" in first
    assert ensure_transported_features(db_session, stranger) == first  # stored, never re-rolled

    lines = people_present_lines(db_session, state)
    assert lines[0] == "PESSOAS PRESENTES" and len(lines) == 1 + len(present_people(state))
    assert "P1:" in lines[1]


def test_the_parser_reference_picks_the_person_and_the_intent_context_is_slim(db_session):
    campaign, character = _world(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    kind, person = person_for_ref(state, "P2")
    assert (kind, person) == present_people(state)[1]
    assert person_for_ref(state, "P99") is None and person_for_ref(state, None) is None

    slim = build_intent_context(db_session, state, "CURRENT PLAYER\nName: Logan\n\nPLAYER KNOWLEDGE\n- muito texto")
    assert slim.startswith("PESSOAS PRESENTES") and "CURRENT PLAYER" in slim and "PLAYER KNOWLEDGE" not in slim


def test_talking_to_the_person_the_parser_chose_from_the_description(db_session):
    campaign, character = _world(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    index, stranger = next(
        (index, person) for index, (kind, person) in enumerate(present_people(state), start=1)
        if kind == "simulated_player"
    )
    llm = _Parser(f"P{index}")

    result = engine.resolve_action(
        db_session, llm, campaign.id, character.id,
        'Falo com a pessoa de cabelo escuro que chegou comigo: "Oi!"', intent_llm_service=llm,
    )

    assert f"conversa com {stranger.name}" in result.mechanical_summary


def test_an_ambiguous_reference_is_asked_about_not_narrated(db_session):
    campaign, character = _world(db_session)
    llm = _Parser(None)

    result = engine.resolve_action(
        db_session, llm, campaign.id, character.id, '"Oi, tudo bem?"', intent_llm_service=llm,
    )

    assert result.mechanical_summary.startswith(engine.WHO_DO_YOU_MEAN_PREFIX)
    assert "homem idoso, cabelo branco" in result.mechanical_summary
    assert result.narrative == result.mechanical_summary and llm.narrations == 0


def test_a_hair_and_sex_description_resolves_without_the_parser(db_session):
    from app.ai.people_present import match_by_appearance
    from app.game.world.generator import gender_for_name

    campaign, character = _world(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    elder = next(npc for npc in state.nearby_npcs if npc.role == "ancião da vila")

    assert match_by_appearance(db_session, state, "Falo com o senhor de cabelo branco") == ("npc", elder)
    # The village's old woman may be white-haired too; never the elder.
    woman = match_by_appearance(db_session, state, "Falo com a senhora de cabelo branco")
    assert woman is None or (woman[1] is not elder and gender_for_name(woman[1].name) == "F")
    assert match_by_appearance(db_session, state, "Olho ao redor") is None
