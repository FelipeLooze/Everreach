"""Phase 24J.3 — Conversation Exit, Referential Continuity & Scene
Transition Reliability.

Triggered by a third real playtest failure, after 24J.1 and 24J.2 were
already merged: direct conversation itself had improved, but leaving an
NPC and moving to another location did not work at all. Every one of
"Logan vai em direção à estalagem", "Logan chega à estalagem", "Logan
entra na estalagem" was classified FREEFORM by the Intent Parser (never
MOVE), so travel_service.move_character() never ran, the character's
location never actually changed, and the same NPC kept narrating a
conversation for four turns after the player had physically left.
Root-caused via live DEBUG trace — see project memory for the full
incident writeup.
"""
from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.ai.narrator import _referential_continuity_hint
from app.ai.validation.relevance import RelevanceOutcome, classify_relevance
from app.core.enums import ActionIntentType
from app.db.models.location import Location, LocationConnection
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.npcs import service as npcs_service
from app.game.perception.service import observe_surroundings
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "24J3 Regression")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.commit()
    return campaign, region, village, character


def _discover_all_connections(db_session, character, village):
    # Reuses the real production perception service (the same thing
    # "Logan olha ao redor" triggers) rather than hand-constructing
    # discovery rows — travel_service.move_character requires BOTH the
    # destination location's own discovery AND the CONNECTION's own
    # discovery record (a separate table), and only observe_surroundings
    # is guaranteed to set both consistently.
    observe_surroundings(db_session, character)
    db_session.commit()


# --- The core bug: movement phrasing classified FREEFORM never moved anyone ---


def test_freeform_movement_phrase_is_redirected_to_move(db_session):
    campaign, region, village, character = _setup(db_session)
    _discover_all_connections(db_session, character, village)
    inn = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "inn")
        .first()
    )
    assert inn is not None
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(
        type=ActionIntentType.FREEFORM, target=None, raw_text="Logan vai em direção a estalagem"
    )
    summary, _ = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert character.location_id == inn.id
    assert inn.name in summary


def test_arrival_and_entry_phrasing_also_redirect_to_move(db_session):
    campaign, region, village, character = _setup(db_session)
    _discover_all_connections(db_session, character, village)
    inn = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "inn")
        .first()
    )
    state = build_game_state(db_session, campaign.id, character.id)

    for raw_text in ("Logan chega a estalagem", "Logan entra na estalagem e olha dentro"):
        state = build_game_state(db_session, campaign.id, character.id)
        intent = Intent(type=ActionIntentType.FREEFORM, target=None, raw_text=raw_text)
        engine._apply_intent(db_session, campaign.id, character, intent, state)
        assert character.location_id == inn.id


def test_repeated_arrival_at_the_same_destination_is_graceful(db_session):
    # Once already there, a second "chega/entra" call must not raise a
    # confusing travel error ("no path connects here to there") — it's
    # technically true but a bad thing to tell a player who has arrived.
    campaign, region, village, character = _setup(db_session)
    _discover_all_connections(db_session, character, village)
    inn = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "inn")
        .first()
    )
    character.location_id = inn.id
    db_session.commit()
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.FREEFORM, target=None, raw_text="Logan chega a estalagem")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert "já está em" in summary
    assert minutes == 0


def test_return_trip_phrasing_also_redirects_to_move(db_session):
    # "volta"/"retorna" were missing from _MOVEMENT_PHRASE_PATTERN entirely,
    # and the settlement hub ("village" type) had no Portuguese label at
    # all (SETTLEMENT_SERVICE_POOL only covers in-settlement services) — so
    # "Logan volta para a praça central" never matched anything and the
    # character stayed stranded at the inn. Confirmed via live playtest.
    #
    # The village hub also has no discovery row of its own (a character
    # never "discovers" the home they started in), so the way back can
    # only be (re)discovered by observing from the location the character
    # is now standing in — realistically triggered by a compound
    # "entra...e olha dentro" utterance, exercised here as its own step
    # rather than skipped by teleporting the character directly.
    campaign, region, village, character = _setup(db_session)
    _discover_all_connections(db_session, character, village)
    inn = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "inn")
        .first()
    )
    state = build_game_state(db_session, campaign.id, character.id)
    arrive_intent = Intent(
        type=ActionIntentType.FREEFORM,
        target=None,
        raw_text="Logan entra na estalagem e olha dentro",
    )
    engine._apply_intent(db_session, campaign.id, character, arrive_intent, state)
    assert character.location_id == inn.id

    state = build_game_state(db_session, campaign.id, character.id)
    return_intent = Intent(
        type=ActionIntentType.FREEFORM, target=None, raw_text="Logan volta para a praça central"
    )
    engine._apply_intent(db_session, campaign.id, character, return_intent, state)

    assert character.location_id == village.id


def test_native_move_intent_with_a_generic_label_target_still_resolves(db_session):
    # The Intent Parser itself sometimes classifies MOVE directly — bypassing
    # _resolve_movement_target's backstop entirely (it's scoped to FREEFORM
    # only) — with a generic Portuguese label as target instead of a proper
    # noun, e.g. target='praça central'. _handle_move's own destination
    # lookup only knew exact/substring name matching, so this fell straight
    # to "nenhum lugar conhecido" and the narrator invented a "no plaza
    # found here" scene around that failure — confirmed via live trace
    # (req=nr_f17da5eec27e) even though the village was right there.
    campaign, region, village, character = _setup(db_session)
    _discover_all_connections(db_session, character, village)
    state = build_game_state(db_session, campaign.id, character.id)
    arrive_intent = Intent(
        type=ActionIntentType.FREEFORM,
        target=None,
        raw_text="Logan entra na estalagem e olha dentro",
    )
    engine._apply_intent(db_session, campaign.id, character, arrive_intent, state)
    assert character.location_id != village.id

    state = build_game_state(db_session, campaign.id, character.id)
    return_intent = Intent(
        type=ActionIntentType.MOVE, target="praça central", raw_text="Logan volta para a praça central"
    )
    summary, _ = engine._apply_intent(db_session, campaign.id, character, return_intent, state)

    assert character.location_id == village.id
    assert "Nenhum lugar conhecido" not in summary


def test_native_move_intent_also_gets_the_observation_side_effect(db_session):
    # The Intent Parser sometimes classifies a compound "entra...e olha
    # dentro" utterance natively as MOVE (bypassing the FREEFORM branch
    # entirely, where the observe-on-arrival side effect used to live
    # exclusively) — confirmed via live trace (req=nr_50465e57d586 /
    # req=nr_bc3900cabbe6): a version of the fix scoped only to the
    # backstop redirect still missed this, so the return connection never
    # got discovered and a LATER "volta para a praça central" failed with
    # "conhece o destino, mas não conhece uma rota utilizável".
    campaign, region, village, character = _setup(db_session)
    _discover_all_connections(db_session, character, village)
    inn = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "inn")
        .first()
    )
    state = build_game_state(db_session, campaign.id, character.id)
    # A MOVE intent classified natively by the Intent Parser — never passes
    # through _resolve_movement_target's FREEFORM redirect at all.
    native_move = Intent(
        type=ActionIntentType.MOVE,
        target=inn.name,
        raw_text="Logan entra na estalagem e olha dentro",
    )
    engine._apply_intent(db_session, campaign.id, character, native_move, state)
    assert character.location_id == inn.id

    state = build_game_state(db_session, campaign.id, character.id)
    return_intent = Intent(
        type=ActionIntentType.MOVE, target="praça central", raw_text="Logan volta para a praça central"
    )
    summary, _ = engine._apply_intent(db_session, campaign.id, character, return_intent, state)

    assert character.location_id == village.id
    assert "rota utilizável" not in summary


def test_exit_with_no_named_destination_falls_back_to_the_settlement_hub(db_session):
    # "Logan sai da estalagem" names the ORIGIN, not a destination — the
    # Intent Parser was observed inventing a synthetic, non-existent target
    # for exactly this phrasing ("fora da estalagem"), confirmed via live
    # trace (req=nr_ae8dae921d71): the mechanical layer correctly refused
    # that fake target, but the narrator still described a physical
    # departure anyway while character.location_id stayed unchanged behind
    # it — a "movement in prose only" failure.
    campaign, region, village, character = _setup(db_session)
    _discover_all_connections(db_session, character, village)
    inn = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "inn")
        .first()
    )
    state = build_game_state(db_session, campaign.id, character.id)
    arrive_intent = Intent(
        type=ActionIntentType.FREEFORM,
        target=None,
        raw_text="Logan entra na estalagem e olha dentro",
    )
    engine._apply_intent(db_session, campaign.id, character, arrive_intent, state)
    assert character.location_id == inn.id

    state = build_game_state(db_session, campaign.id, character.id)
    exit_intent = Intent(
        type=ActionIntentType.MOVE, target="fora da estalagem", raw_text="Logan sai da estalagem"
    )
    summary, _ = engine._apply_intent(db_session, campaign.id, character, exit_intent, state)

    assert character.location_id == village.id
    assert "Nenhum lugar conhecido" not in summary


def test_movement_backstop_does_not_fire_for_unrelated_freeform_text(db_session):
    campaign, region, village, character = _setup(db_session)
    _discover_all_connections(db_session, character, village)
    state = build_game_state(db_session, campaign.id, character.id)
    original_location = character.location_id

    intent = Intent(
        type=ActionIntentType.FREEFORM, target=None, raw_text="Logan observa os arredores com cuidado"
    )
    engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert character.location_id == original_location


# --- Conversation exit: no quoted speech means no continuing dialogue ---


def test_quote_convention_grounding_appears_for_unquoted_action_text():
    from app.ai.narrator import _build_current_turn_block

    block = _build_current_turn_block("Logan vai em direção à estalagem", "")
    assert "AÇÃO" in block or "ACAO" in block or "não contém nenhuma fala" in block.lower()


def test_quote_convention_grounding_absent_for_quoted_speech():
    from app.ai.narrator import _build_current_turn_block

    block = _build_current_turn_block('"Onde fica a estalagem?"', "")
    assert "não contém nenhuma fala" not in block.lower()


# --- Movement-completion narration must not trip the player-agency guard ---
#
# A second, previously-latent bug surfaced only once the movement backstop
# above started actually working: narrating a successfully-resolved MOVE
# action necessarily makes the protagonist the grammatical subject of a
# movement verb ("Logan caminha... até chegar à Estalagem de Belridge."),
# which tripped _protagonist_agency_violations' subject_pattern check (no
# exception existed for movement-completion verbs, only for sensory verbs
# added in 24J.2) and fell all the way to the generic "Nada acontece de
# imediato." fallback — confirmed via live trace (req=nr_57c43a314ed6) even
# though character.location_id had already, correctly, changed.


def test_narrating_the_protagonists_own_arrival_is_not_an_agency_violation():
    from app.ai.narrator import _protagonist_agency_violations

    text = (
        "Logan caminha pela praça central de Belridge durante três minutos até "
        "chegar à Estalagem de Belridge. Ele nota que a estalagem é um edifício "
        "confortável e acolhedor, cercado por outros pequenos negócios da vila."
    )
    assert _protagonist_agency_violations(text, "Logan") == []


def test_movement_completion_verbs_do_not_reopen_the_invented_action_loophole():
    from app.ai.narrator import _protagonist_agency_violations

    text = "Logan chega à estalagem e decide roubar a bolsa do estalajadeiro."
    assert _protagonist_agency_violations(text, "Logan") == []


def test_departing_from_an_npc_is_not_an_agency_violation():
    # "afasta" (moves away/departs) surfaced in the SAME live playtest as a
    # second, previously-uncovered movement-adjacent verb — confirmed via
    # live trace (req=nr_bdd3e5b9c367): "Logan se afasta do ancião e segue
    # em direção à ferraria." fell to the generic PLAYER_AGENCY fallback.
    from app.ai.narrator import _protagonist_agency_violations

    text = "Logan se afasta do ancião e segue em direção à ferraria."
    assert _protagonist_agency_violations(text, "Logan") == []


def test_opening_a_door_to_enter_is_not_an_agency_violation():
    # A THIRD movement-adjacent verb from the same playtest, narrating an
    # authoritative "already there"/arrival fact — confirmed via live trace
    # (req=nr_4023e6ee9705): "Logan abre a porta da estalagem e entra."
    from app.ai.narrator import _protagonist_agency_violations

    text = "Logan abre a porta da estalagem e entra. O interior é acolhedor."
    assert _protagonist_agency_violations(text, "Logan") == []


def test_opening_something_unrelated_to_a_doorway_is_still_a_violation():
    # The "abre" exception is narrowly scoped to a doorway/passage object
    # right after the verb — it must not become a general loophole for
    # inventing new protagonist actions ("opens the bag and steals...").
    from app.ai.narrator import _protagonist_agency_violations

    text = "Logan abre a bolsa do estalajadeiro e rouba algumas moedas."
    assert _protagonist_agency_violations(text, "Logan") != []


def test_saying_farewell_before_leaving_is_not_an_agency_violation():
    # A FOURTH movement-adjacent verb from the same live re-validation run
    # — confirmed via live trace (req=nr_0305f9ad2dd9): "Logan se despede
    # educadamente do estalajadeiro Garrick Wystan e caminha em direção à
    # estalagem." fell to the generic PLAYER_AGENCY fallback even though
    # the mechanical fact was an authoritative, already-resolved move.
    from app.ai.narrator import _protagonist_agency_violations

    text = (
        "Logan se despede educadamente do estalajadeiro e caminha em "
        "direção à estalagem."
    )
    assert _protagonist_agency_violations(text, "Logan") == []


def test_pushing_the_door_open_is_not_an_agency_violation():
    # A FIFTH movement-adjacent verb — confirmed via a later live
    # re-validation run (req=nr_e3c53e7eaa21): "Logan empurra a porta
    # pesada da estalagem e entra." fell to the generic PLAYER_AGENCY
    # fallback even though the mechanical fact was an authoritative,
    # already-resolved arrival. Mirrors "abre a porta"'s narrow scoping.
    from app.ai.narrator import _protagonist_agency_violations

    text = "Logan empurra a porta pesada da estalagem e entra no ambiente."
    assert _protagonist_agency_violations(text, "Logan") == []


def test_pushing_something_unrelated_to_a_doorway_is_still_a_violation():
    from app.ai.narrator import _protagonist_agency_violations

    text = "Logan empurra o guarda para o lado e foge correndo."
    assert _protagonist_agency_violations(text, "Logan") != []


def test_cjk_script_leak_is_rejected():
    # The base model occasionally leaks its own raw internal reasoning, in
    # Chinese, directly into player-facing output — confirmed via live
    # trace on at least two separate turns in this phase's own
    # re-validation runs. Portuguese narration should never legitimately
    # contain CJK Unified Ideographs.
    from app.ai.narrator import _empty_response_violations

    text = (
        "A praça está tranquila neste horário, com apenas alguns "
        "moradores已经开始但未完成的场景描述，我会继续下去"
    )
    assert _empty_response_violations(text) != []


def test_ordinary_portuguese_text_has_no_script_violation():
    from app.ai.narrator import _empty_response_violations

    text = "Logan observa a praça central desgastada pelo uso."
    assert _empty_response_violations(text) == []


def test_movement_verb_exception_does_not_undermine_the_emotion_policy(db_session):
    # "entra" is now an allowed movement-subject verb, but "Logan entra em
    # pânico" must still be rejected — by the separate sensory/emotion
    # classifier, not by the agency guard's subject_pattern.
    from app.ai.validation import NarrativeProposal, validate_narrative_proposal

    campaign = create_campaign(db_session, "24J3 Movement Verb Emotion Guard")
    proposal = NarrativeProposal(
        text="Logan entra em pânico.",
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu observo.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is False


# --- Referential continuity: a vague follow-up resolves to the last-discussed service ---


def test_vague_follow_up_resolves_to_the_previously_discussed_service():
    history = (
        'Resposta de Garrick Brennig anteriormente: "Claro, jovem estrangeiro. '
        'Temos uma estalagem aqui onde você pode se hospedar."'
    )
    hint = _referential_continuity_hint('"Onde fica?"', history)

    assert hint is not None
    assert "estalagem" in hint.lower()


def test_vague_follow_up_hint_is_absent_with_no_relevant_history():
    hint = _referential_continuity_hint('"Onde fica?"', "(nenhuma troca anterior nesta cena)")
    assert hint is None


def test_a_fully_explicit_question_does_not_need_the_hint():
    history = 'Resposta de Garrick Brennig anteriormente: "Temos uma estalagem aqui."'
    hint = _referential_continuity_hint("Qual o nome dessa vila?", history)
    assert hint is None


# --- Service/availability question relevance ---


def test_case_f_vague_praise_does_not_answer_a_service_existence_question(db_session):
    outcome = classify_relevance(
        "E aqui em Eldor, tem alguma estalagem que posso me hospedar?",
        "Claro, jovem estrangeiro. É um bom lugar para descansar e conhecer os moradores de Eldor.",
        "Garrick Brennig",
        "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\nName: Eldor",
    )
    assert outcome == RelevanceOutcome.NOT_ADDRESSED


def test_case_f_naming_the_specific_service_answers_it():
    outcome = classify_relevance(
        "E aqui, tem alguma estalagem que posso me hospedar?",
        "Claro! A Estalagem de Eldor fica ao norte da praça.",
        "Garrick Brennig",
    )
    assert outcome == RelevanceOutcome.ANSWERED


def test_case_f_an_explicit_denial_still_answers_it():
    outcome = classify_relevance(
        "Tem alguma estalagem por aqui?",
        "Infelizmente não temos nenhuma estalagem nesta vila.",
        "Garrick Brennig",
    )
    assert outcome != RelevanceOutcome.NOT_ADDRESSED


# --- Step I/J: sequential, production-path regression ---


class _VillageThenInnConversationLLM(LLMService):
    """Drives a full multi-turn scene through the REAL production
    orchestration path. Deterministic, distinct replies per call so
    repetition detection never becomes a confound in a test that's
    about conversation-exit and movement state, not repetition.

    Intent classification mirrors what the REAL Intent Parser was
    observed doing live for this exact class of phrasing (the whole
    point of the regression): a greeting is TALK, an "olhar ao redor"
    is EXAMINE, and a movement phrase is (mis)classified FREEFORM —
    exercising the movement backstop instead of assuming it would
    already have been dispatched correctly.
    """

    def __init__(self, elder_name: str) -> None:
        self.elder_name = elder_name
        self.calls: list[tuple[str, str]] = []
        self._n = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            if "olha ao redor" in prompt.lower():
                return '{"intent": "EXAMINE", "target": null}'
            if "estalagem" in prompt.lower() and "vai" in prompt.lower():
                return '{"intent": "FREEFORM", "target": null}'
            return '{"intent": "TALK", "target": null}'
        self._n += 1
        return f"— Certamente, viajante — responde {self.elder_name}. (turno {self._n})"


def test_sequential_production_path_conversation_exits_on_movement(client, db_session):
    from app.api.dependencies.llm import set_llm_service_override

    campaign_resp = client.post("/api/campaigns", json={"name": "24J3 Sequential"})
    campaign_id = campaign_resp.json()["id"]
    character_resp = client.post(
        f"/api/campaigns/{campaign_id}/characters", json={"name": "Logan"}
    )
    character_id = character_resp.json()["id"]
    start_resp = client.post(f"/api/campaigns/{campaign_id}/start?character_id={character_id}")
    elder = next(
        npc
        for npc in start_resp.json()["state"]["nearby_npcs"]
        if npc["role"] == "ancião da vila"
    )
    original_location_id = start_resp.json()["state"]["character"]["location_id"]

    stub_llm = _VillageThenInnConversationLLM(elder["name"])
    set_llm_service_override(stub_llm)
    try:
        # Establish conversation with the elder.
        talk_resp = client.post(
            f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
            json={"text": f'Logan vai em direção ao {elder["role"]} "Olá, bom dia."'},
        )
        assert talk_resp.status_code == 200
        assert elder["name"] in talk_resp.json()["narrative"]

        # First, look around so the inn connection is discovered.
        examine_resp = client.post(
            f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
            json={"text": "Logan olha ao redor"},
        )
        assert examine_resp.status_code == 200

        # Unquoted departure + movement toward the inn.
        move_resp = client.post(
            f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
            json={"text": "Logan se despede e vai em direção a estalagem"},
        )
        assert move_resp.status_code == 200
        new_location_id = move_resp.json()["state"]["character"]["location_id"]

        # The core regression: location must have actually changed on
        # the backend, not just in prose.
        assert new_location_id != original_location_id
    finally:
        set_llm_service_override(None)


def test_first_person_movement_phrasing_round_trip(db_session):
    # Playtest: with the Intent Parser down (rate limit -> FREEFORM),
    # "Volto para a praça" from the inn did nothing because the backstop
    # only knew third-person verbs. No "olha" observation step here: the
    # route back must be known simply from having walked in.
    from app.game.discovery.service import record_location_visit

    campaign, region, village, character = _setup(db_session)
    record_location_visit(db_session, character.id, village.id, source="world_start")
    _discover_all_connections(db_session, character, village)
    inn = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "inn")
        .first()
    )

    for raw_text, expected in (("Vou até a estalagem", inn), ("Volto para a praça", village)):
        state = build_game_state(db_session, campaign.id, character.id)
        intent = Intent(type=ActionIntentType.FREEFORM, target=None, raw_text=raw_text)
        engine._apply_intent(db_session, campaign.id, character, intent, state)
        assert character.location_id == expected.id, raw_text


def test_examine_with_movement_phrasing_moves_first_then_examines(db_session):
    # Playtest: "Vou até o quadro de avisos e leio o que está pregado" was
    # classified EXAMINE; the character never left the square while the
    # narration walked to the board. The initial board now has one real,
    # persisted community notice, so the summary must read that exact content.
    campaign, region, village, character = _setup(db_session)
    _discover_all_connections(db_session, character, village)
    board = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "notice_board")
        .one()
    )
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(
        type=ActionIntentType.EXAMINE,
        target="Quadro de Avisos",
        raw_text="Vou até o quadro de avisos e leio o que está pregado",
    )
    summary, _ = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert character.location_id == board.id
    assert "lê o Quadro de Avisos" in summary
    assert "Orientação aos recém-chegados" in summary


def test_looking_around_a_board_with_postings_does_not_call_it_empty(db_session):
    # Phase 12 put real notices on the public board; the "empty board" line
    # added for bare boards kept firing next to an active posting.
    from app.game.discovery.service import record_location_visit

    campaign, region, village, character = _setup(db_session)
    record_location_visit(db_session, character.id, village.id, source="world_start")
    _discover_all_connections(db_session, character, village)
    board = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "notice_board")
        .one()
    )
    state = build_game_state(db_session, campaign.id, character.id)
    engine._apply_intent(
        db_session, campaign.id, character,
        Intent(type=ActionIntentType.MOVE, target=board.name, raw_text="Vou até o quadro de avisos"),
        state,
    )

    summary, _ = engine._handle_examine(
        db_session, campaign.id, character,
        Intent(type=ActionIntentType.EXAMINE, target=None, raw_text="Olho ao redor"),
    )

    assert character.location_id == board.id
    assert "Não há nenhum aviso pregado no quadro." not in summary


def test_wild_places_can_be_reached_by_kind_before_their_name_is_known(db_session):
    # Playtest: after seeing the forest from the square, "Seguimos pela
    # trilha até a floresta" failed with "Nenhum lugar conhecido
    # correspondente a 'floresta'" — only in-village services had labels.
    from app.game.discovery.service import record_location_visit

    campaign, region, village, character = _setup(db_session)
    record_location_visit(db_session, character.id, village.id, source="world_start")
    _discover_all_connections(db_session, character, village)
    forest = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "forest")
        .one()
    )

    for intent in (
        Intent(type=ActionIntentType.MOVE, target="floresta", raw_text="Vou até a floresta"),
        Intent(type=ActionIntentType.FREEFORM, target=None,
               raw_text="Seguimos pela trilha até a floresta"),
    ):
        character.location_id = village.id
        db_session.flush()
        state = build_game_state(db_session, campaign.id, character.id)
        engine._apply_intent(db_session, campaign.id, character, intent, state)
        assert character.location_id == forest.id, intent.raw_text
