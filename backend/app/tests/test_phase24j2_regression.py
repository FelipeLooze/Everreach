"""Phase 24J.2 — Interlocutor Persistence & Action-to-Dialogue Contract.

Triggered by a second real playtest failure, after Phase 24J.1 was
already merged: a player greeted a village elder by ROLE only ("o velho
ancião", never typing his name), got a correct-looking reply, then had
every follow-up question ("qual o nome dessa vila", "há uma estalagem
por perto", "onde estamos") answered with "Nada acontece de imediato."
or a fabricated echo of the player's own words. Root-caused via live
DEBUG trace (never guessed) — see project memory for the full incident
writeup. Every fix here was verified against the real model afterward
(qwen2.5:14b-instruct-q4_K_M, 21 live turns, zero fallbacks).
"""
from app.ai.llm_service import LLMService
from app.ai.intent_parser import Intent
from app.core.enums import ActionIntentType, ConnectionType, connection_type_label_pt
from app.db.models.location import LocationConnection
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.perception.service import observe_surroundings
from app.game.world.seed import create_campaign, seed_initial_region
from app.ai import narrator


def _setup(db_session):
    campaign = create_campaign(db_session, "24J2 Regression")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.commit()
    return campaign, region, village, character


# --- The core bug: role-only reference on a TALK-classified intent ---


def test_role_only_reference_resolves_on_a_talk_classified_intent(db_session):
    # The exact live failure: "Logan vai em direção ao velho ancião..."
    # was classified TALK (not FREEFORM) with an Intent-Parser-GUESSED
    # target the player never typed — _handle_talk correctly refused to
    # trust that guess, but (before this fix) never tried resolving the
    # ROLE reference ("ancião") against the raw text at all, so the elder
    # was never established as active interlocutor.
    campaign, region, village, character = _setup(db_session)
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(
        type=ActionIntentType.TALK,
        target="Some Guessed Name",  # never typed by the player
        raw_text='Logan vai em direção ao velho ancião "Olá, bom dia, senhor. Como está?"',
    )
    summary, _ = engine._handle_talk(db_session, campaign.id, character, intent, state)

    assert elder.name in summary
    assert "Há mais de uma pessoa aqui" not in summary


def test_role_reference_works_even_without_the_filler_words(db_session):
    # "velho ancião" never contains the registered role string verbatim
    # ("ancião da vila") — a first version of this fix required an exact
    # full-phrase match and silently never matched this extremely common,
    # natural abbreviation. Only the role's HEAD word should be required.
    campaign, region, village, character = _setup(db_session)
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.TALK, target=None, raw_text="Falo com o ancião.")
    summary, _ = engine._handle_talk(db_session, campaign.id, character, intent, state)

    assert elder.name in summary


def test_natural_age_reference_resolves_the_village_elder(db_session):
    campaign, region, village, character = _setup(db_session)
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(
        type=ActionIntentType.TALK,
        target="homem idoso",
        raw_text="Ir falar com o homem idoso.",
    )
    summary, _ = engine._handle_talk(db_session, campaign.id, character, intent, state)

    assert elder.name in summary
    assert "Não há ninguém correspondente" not in summary


def test_unique_local_reference_ignores_nearby_transportees(db_session):
    campaign, region, village, character = _setup(db_session)
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    state = build_game_state(db_session, campaign.id, character.id)

    npc, transported = engine._resolve_addressed_entity(
        "Procurar alguém que parece ser dali e ir falar com ele.",
        [elder],
        state.nearby_simulated_players,
    )

    assert npc is elder
    assert transported is None


def test_role_head_word_match_does_not_falsely_match_on_filler_words(db_session):
    # The head-word fix must not become too loose: "vila" alone (part of
    # "ancião DA VILA") is an extremely common word that appears in
    # totally unrelated sentences — matching on it would wrongly resolve
    # the elder whenever the player says "vila" for any reason at all.
    campaign, region, village, character = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(
        type=ActionIntentType.TALK, target=None, raw_text="Qual o nome dessa vila mesmo?"
    )
    summary, _ = engine._handle_talk(db_session, campaign.id, character, intent, state)

    # No role/name reference at all and no active interlocutor yet ->
    # genuinely ambiguous, must ask, never silently guess the elder.
    assert "Há mais de uma pessoa aqui" in summary


# --- Sensory perception verbs must not trip the agency guard ---


def test_examine_narration_with_sensory_verbs_is_not_an_agency_violation():
    # The exact live failure: a plain "Olhar ao redor" action's own
    # mechanical summary literally starts "Logan observa os arredores de
    # X..." — narration opening the same natural way was rejected as a
    # player-agency violation on that basis alone, falling all the way to
    # "Nada acontece de imediato." for legitimate scene description.
    text = (
        "Logan observa a praça central desgastada pelo uso, cercada por "
        "casas de madeira e sapê. Ele nota várias pessoas ao seu redor."
    )
    violations = narrator._protagonist_agency_violations(text, "Logan", mode="CONTINUATION")

    assert violations == []


def test_examine_narration_still_catches_real_agency_violations():
    # The sensory-verb exception must stay narrow — a real invented
    # action/decision right after the character's name is still caught.
    text = "Logan decide atacar o estranho sem hesitar."
    violations = narrator._protagonist_agency_violations(text, "Logan", mode="CONTINUATION")

    assert violations != []


# --- Route descriptions must respect the hidden-name system ---


def test_route_type_label_is_portuguese_and_matches_the_canon_checks_own_vocabulary(db_session):
    # The canon validator's own route-kind+direction check (narrator.py)
    # looks for the Portuguese nouns "estrada"/"trilha" paired with a
    # direction to decide whether a response invented an unauthorized
    # geographic combination. The raw English enum value ("ROAD"/"PATH")
    # used to leak straight into player/LLM-facing text, so that check
    # could never find a match — and rejected the model's own correct
    # Portuguese translation as "invented," confirmed via live trace.
    assert connection_type_label_pt(ConnectionType.ROAD) == "estrada"
    assert connection_type_label_pt(ConnectionType.PATH) == "trilha"


def test_perceived_routes_hide_an_unknown_destination_name(db_session):
    # observe_surroundings' own route text previously revealed a
    # destination's canonical name unconditionally — no gate at all —
    # while the parallel context_builder section already redacted it.
    # Confirmed via live trace: "PATH para Estalagem de Morven" was fed
    # to the narrator as an AUTHORITATIVE FACT before the player had ever
    # learned that settlement's name.
    campaign, region, village, character = _setup(db_session)
    connection = (
        db_session.query(LocationConnection)
        .filter(LocationConnection.from_location_id == village.id)
        .first()
    )
    assert connection is not None

    result = observe_surroundings(db_session, character)

    assert result.location_name_known is False
    for route in result.routes:
        assert village.name not in route
    joined_routes = " ".join(result.routes)
    for word in ("Estalagem", "Loja Geral", "Ferraria"):
        # None of the destination's own private proper-noun components
        # should leak into perceptible route text before it's learned.
        assert word not in joined_routes or "desconhecido" in joined_routes


# --- Step 6/11: sequential, production-path regression ---


class _RoleGreetingConversationLLM(LLMService):
    """Drives a full multi-turn conversation through the REAL production
    orchestration path (intent parsing -> engine -> narration ->
    validation -> persistence), per the spec's own explicit instruction
    not to test narrator.narrate() or a validator in isolation. Never
    guesses a literal target for TALK (mirrors the real Intent Parser's
    own occasional behavior that triggered this regression) and returns
    a distinct, safe, agency/canon-clean reply every call so repetition
    detection never becomes a confound in a test that's about
    continuity, not repetition."""

    def __init__(self, elder_name: str) -> None:
        self.elder_name = elder_name
        self.calls: list[tuple[str, str]] = []
        self._n = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            return '{"intent": "TALK", "target": null}'
        self._n += 1
        return f"— Certamente, viajante — responde {self.elder_name}. (turno {self._n})"


def test_sequential_production_path_keeps_the_same_interlocutor(client, db_session):
    # The exact reported sequence, run through POST /actions (the real
    # entrypoint), not a unit-level helper. TURN 1 addresses the elder by
    # role only; TURNS 2-4 never re-name him. Every turn must stay with
    # the SAME NPC and none may ever produce "Nada acontece de imediato."
    from app.api.dependencies.llm import set_llm_service_override

    campaign_resp = client.post("/api/campaigns", json={"name": "24J2 Sequential"})
    assert campaign_resp.status_code == 200
    campaign_id = campaign_resp.json()["id"]

    character_resp = client.post(
        f"/api/campaigns/{campaign_id}/characters", json={"name": "Logan"}
    )
    assert character_resp.status_code == 200
    character_id = character_resp.json()["id"]

    start_resp = client.post(f"/api/campaigns/{campaign_id}/start?character_id={character_id}")
    assert start_resp.status_code == 200
    elder = next(
        npc
        for npc in start_resp.json()["state"]["nearby_npcs"]
        if npc["role"] == "ancião da vila"
    )

    stub_llm = _RoleGreetingConversationLLM(elder["name"])
    set_llm_service_override(stub_llm)
    try:
        turns = [
            'Logan vai em direção ao velho ancião "Olá, bom dia, senhor. Como está?"',
            '"Gostaria de saber qual o nome dessa vila que nos encontramos" pergunta Logan',
            '"O senhor saberia me informar se há alguma estalagem por perto?"',
            '"Onde estamos?"',
        ]
        for turn_text in turns:
            response = client.post(
                f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
                json={"text": turn_text},
            )
            assert response.status_code == 200
            narrative = response.json()["narrative"]

            assert narrative != "Nada acontece de imediato."
            assert elder["name"] in narrative
    finally:
        set_llm_service_override(None)
