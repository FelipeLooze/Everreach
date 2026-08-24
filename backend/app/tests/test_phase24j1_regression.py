"""Phase 24J.1 — Broad Conversational Reliability & Active Interlocutor
Reliability. Permanent regression coverage for the 10 named cases (A-J)
the subphase's own spec required, tied directly to a REAL failed live
playtest transcript (a player asked local NPCs "que vila é essa?"/
"qual o nome dessa vila?" and got silence, then a repeated generic
greeting closer, plus an active-interlocutor continuity break on an
unnamed follow-up). Every fix here was root-caused via live trace before
being written — see project memory for the full incident writeup.
"""
from app.ai import context_builder, narrator
from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.ai.validation.relevance import RelevanceOutcome, classify_relevance
from app.core.enums import ActionIntentType
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.npcs import service as npcs_service
from app.game.players import service as players_service
from app.game.world.seed import create_campaign, seed_initial_region


def _proposal(text: str, player_input: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context=(
            "CURRENT PLAYER\nName: Logan\n\n"
            "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\n"
            "Name: Karvale\nType: VILLAGE\nRegion: Campos de Kessler\n\n"
            "ACTIVE NPC CONTEXT\nName: Perrin Ferrow\nLocation: Karvale"
        ),
        mechanical_summary="",
        player_input=player_input,
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
        active_npc_id="npc_fake",
        active_npc_name="Perrin Ferrow",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def _setup(db_session):
    campaign = create_campaign(db_session, "24J1 Regression")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.commit()
    return campaign, region, village, character


class RepeatingLLM(LLMService):
    """Always returns the same text, regardless of prompt — the worst
    case for the repair pipeline: the model never self-corrects, so any
    fix has to come from the backend, not from hoping revision helps."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.response


# --- Case A: village-name question answered ---


def test_case_a_village_name_question_is_answered(db_session):
    campaign = create_campaign(db_session, "Caso A")
    proposal = _proposal("— Isto aqui é Karvale — responde Perrin.", "Qual o nome dessa vila?")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
    assert "Karvale" in result.final_text


# --- Case B: same question after a generic greeting must not just repeat it ---


def test_case_b_repeated_generic_response_is_not_returned_again():
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\nName: Karvale\n\n"
        "ACTIVE NPC CONTEXT\nName: Perrin Ferrow\n\n"
        "DIRECT QUESTION GROUNDING\n"
        "The player is asking for the CURRENT location/settlement's name.\n"
        "Authorized answer: Karvale"
    )
    history = 'Resposta de Perrin Ferrow anteriormente: "Como posso ajudar você hoje?"'
    llm = RepeatingLLM("Como posso ajudar você hoje?")

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "Qual o nome dessa vila?", history
    )

    assert result != "Como posso ajudar você hoje?"
    assert "Karvale" in result


# --- Case C: implicit follow-up keeps the same interlocutor ---


def test_case_c_implicit_follow_up_keeps_same_interlocutor(db_session):
    campaign, region, village, character = _setup(db_session)
    innkeeper = db_session.query(NPC).filter(NPC.role == "estalajadeiro").first()
    state = build_game_state(db_session, campaign.id, character.id)

    first_intent = Intent(
        type=ActionIntentType.TALK,
        target=innkeeper.name,
        raw_text=f'Falo com {innkeeper.name}: "Olá, tudo bem?"',
    )
    summary, _ = engine._apply_intent(db_session, campaign.id, character, first_intent, state)
    assert innkeeper.name in summary

    state = build_game_state(db_session, campaign.id, character.id)
    follow_up = Intent(type=ActionIntentType.TALK, target=None, raw_text='"Qual o seu nome mesmo?"')
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, follow_up, state)

    assert innkeeper.name in summary
    assert "Há mais de uma pessoa aqui" not in summary


# --- Case C2: a FREEFORM-classified "approach + speak" sentence also switches interlocutor ---


def test_case_c2_freeform_explicit_approach_switches_active_interlocutor(db_session):
    # A deeper form of Case C, found via the live 18-turn playtest: a
    # compound "approach + speak" sentence ("Logan se aproxima de X e
    # pergunta...") is routinely classified FREEFORM (not TALK) by the
    # Intent Parser — before this fix, that meant the active
    # interlocutor's PERSISTED state never advanced at all, even though
    # the player's own words unambiguously named a specific nearby NPC.
    # Live evidence: a full turn of dialogue got voiced by the newly-
    # approached NPC while the backend's own tracked active interlocutor
    # silently stayed on the previous one, and the very next follow-up
    # (with no name to lean on) reverted right back to that stale NPC.
    campaign, region, village, character = _setup(db_session)
    innkeeper = db_session.query(NPC).filter(NPC.role == "estalajadeiro").first()
    blacksmith = db_session.query(NPC).filter(NPC.role == "ferreira").first()
    # The world seed's random name generator occasionally reuses a first
    # or last name across different NPCs in the same village — pin fixed,
    # guaranteed-distinct names so this regression test's own assertions
    # never depend on that randomness (an accidental collision would make
    # the match correctly, conservatively ambiguous, per _handle_talk's
    # own "never guess" philosophy — a real behavior worth having, but
    # not what this specific test is about).
    innkeeper.name = "Talven Ashgrove"
    blacksmith.name = "Mira Stonewell"
    db_session.flush()
    state = build_game_state(db_session, campaign.id, character.id)

    talk_intent = Intent(
        type=ActionIntentType.TALK, target=innkeeper.name, raw_text=f'Falo com {innkeeper.name}: "Olá"'
    )
    engine._apply_intent(db_session, campaign.id, character, talk_intent, state)

    state = build_game_state(db_session, campaign.id, character.id)
    freeform_intent = Intent(
        type=ActionIntentType.FREEFORM,
        target=None,
        raw_text=f'Logan se aproxima de {blacksmith.name} e pergunta: "Qual o nome dessa vila?"',
    )
    switched_npc, switched_simulated_player = engine._implicit_freeform_interlocutor_switch(
        db_session, campaign.id, character, freeform_intent, state
    )

    assert switched_simulated_player is None
    assert switched_npc is not None
    assert switched_npc.id == blacksmith.id

    active = npcs_service.get_active_interlocutor(
        db_session, campaign.id, character.id, character.location_id
    )
    assert active is not None
    assert active.id == blacksmith.id


def test_case_c2b_freeform_approach_by_role_switches_active_interlocutor(db_session):
    # "o anciao da vila" names no proper noun at all — only a ROLE, and
    # deliberately typed WITHOUT the accent ("anciao", not "ancião") —
    # exactly how the live playtest's own script phrased it. A first
    # version of this fix matched roles only via an exact accented
    # substring check, which silently never matched unaccented player
    # input (a live, confirmed, far-from-rare gap, not an edge case).
    campaign, region, village, character = _setup(db_session)
    innkeeper = db_session.query(NPC).filter(NPC.role == "estalajadeiro").first()
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    state = build_game_state(db_session, campaign.id, character.id)

    talk_intent = Intent(
        type=ActionIntentType.TALK, target=innkeeper.name, raw_text=f'Falo com {innkeeper.name}: "Olá"'
    )
    engine._apply_intent(db_session, campaign.id, character, talk_intent, state)

    state = build_game_state(db_session, campaign.id, character.id)
    freeform_intent = Intent(
        type=ActionIntentType.FREEFORM,
        target=None,
        raw_text='Logan se aproxima do anciao da vila e pergunta: "Bom dia, tudo bem?"',
    )
    switched_npc, switched_simulated_player = engine._implicit_freeform_interlocutor_switch(
        db_session, campaign.id, character, freeform_intent, state
    )

    assert switched_simulated_player is None
    assert switched_npc is not None
    assert switched_npc.id == elder.id


def test_case_c2c_freeform_approach_switches_to_a_simulated_player(db_session):
    # The exact live-playtest scenario: "Logan se afasta de Thane e se
    # aproxima de Corren para conversar" — Corren is a transported
    # SimulatedPlayer, not an NPC. The switch must recognize nearby
    # simulated players too, not just NPCs.
    campaign, region, village, character = _setup(db_session)
    innkeeper = db_session.query(NPC).filter(NPC.role == "estalajadeiro").first()
    state = build_game_state(db_session, campaign.id, character.id)

    innkeeper.name = "Talven Ashgrove"
    db_session.flush()
    talk_intent = Intent(
        type=ActionIntentType.TALK, target=innkeeper.name, raw_text=f'Falo com {innkeeper.name}: "Olá"'
    )
    engine._apply_intent(db_session, campaign.id, character, talk_intent, state)

    state = build_game_state(db_session, campaign.id, character.id)
    freeform_intent = Intent(
        type=ActionIntentType.APPROACH,
        target="Corren Ashvale",
        # Names BOTH the NPC being left AND the simulated player being
        # approached, exactly like the real live-playtest phrasing — a
        # name mentioned only inside "se afasta de ___" must not count as
        # a candidate, or this becomes spuriously ambiguous between the
        # two (a real regression, confirmed via live trace).
        raw_text=(
            f"Logan se afasta de {innkeeper.name} e se aproxima de "
            "Corren Ashvale para conversar"
        ),
    )
    switched_npc, switched_simulated_player = engine._implicit_freeform_interlocutor_switch(
        db_session, campaign.id, character, freeform_intent, state
    )

    assert switched_npc is None
    assert switched_simulated_player is not None
    assert switched_simulated_player.name == "Corren Ashvale"

    active_player = players_service.get_active_simulated_player_interlocutor(
        db_session, campaign.id, character.id, character.location_id
    )
    assert active_player is not None
    assert active_player.name == "Corren Ashvale"


def test_case_c2d_common_word_name_collision_does_not_trigger_a_false_switch(db_session):
    # The world seed's fixed simulated player "Dessa Marrow" is spelled
    # identically to "dessa" — an ordinary, extremely common Portuguese
    # demonstrative ("of/from that") — so an entirely unrelated question
    # like "Qual o nome DESSA vila?" contains that exact word. A bare
    # (even word-boundary) casefolded match would wrongly "switch" the
    # conversation to Dessa Marrow. The player never capitalized "Dessa"
    # as a name here, so no switch should fire at all — falling back to
    # whoever was already the active interlocutor is the correct, safe
    # outcome, exactly like any other no-match case.
    campaign, region, village, character = _setup(db_session)
    innkeeper = db_session.query(NPC).filter(NPC.role == "estalajadeiro").first()
    state = build_game_state(db_session, campaign.id, character.id)

    talk_intent = Intent(
        type=ActionIntentType.TALK, target=innkeeper.name, raw_text=f'Falo com {innkeeper.name}: "Olá"'
    )
    engine._apply_intent(db_session, campaign.id, character, talk_intent, state)

    state = build_game_state(db_session, campaign.id, character.id)
    freeform_intent = Intent(
        type=ActionIntentType.FREEFORM, target=None, raw_text="Qual o nome dessa vila mesmo?"
    )
    switched_npc, switched_simulated_player = engine._implicit_freeform_interlocutor_switch(
        db_session, campaign.id, character, freeform_intent, state
    )

    assert switched_npc is None
    assert switched_simulated_player is None


# --- Case D: transported/unknowing NPC must not doubt being IN a village ---


def test_case_d_location_context_separates_perceptible_type_from_hidden_name(db_session):
    campaign, region, village, character = _setup(db_session)
    context = context_builder.build_context(
        db_session, build_game_state(db_session, campaign.id, character.id)
    )

    assert "Type: VILLAGE (DIRECTLY PERCEPTIBLE" in context
    assert f"Name: {village.name} (HIDDEN" in context


# --- Case E: "Nada acontece de imediato." to an available NPC must be rejected ---


def test_case_e_nothing_happens_fallback_to_available_npc_is_rejected(db_session):
    campaign = create_campaign(db_session, "Caso E")
    proposal = _proposal("Nada acontece de imediato.", "Qual o nome dessa vila?")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


# --- Case F: NPC admitting ignorance is accepted ---


def test_case_f_admitted_ignorance_is_accepted(db_session):
    campaign = create_campaign(db_session, "Caso F")
    proposal = _proposal(
        "— Não sei dizer ao certo o nome desta vila — admite Perrin.", "Qual o nome dessa vila?"
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
    outcome = classify_relevance(
        "Qual o nome dessa vila?",
        "Não sei dizer ao certo o nome desta vila.",
        "Perrin Ferrow",
        proposal.context,
    )
    assert outcome == RelevanceOutcome.ADMITTED_IGNORANCE


# --- Case G: NPC refusing is accepted ---


def test_case_g_explicit_refusal_is_accepted(db_session):
    campaign = create_campaign(db_session, "Caso G")
    proposal = _proposal("— Isso não é da sua conta — resmunga Perrin.", "Qual o nome dessa vila?")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


# --- Case H: NPC lying — relevance passes, Canon/knowledge check truth separately ---


def test_case_h_a_confident_wrong_answer_still_passes_relevance():
    # Perrin confidently states a name that is NOT the registered
    # canonical name ("Karvale") — classify_relevance only checks that
    # the question was engaged with, never whether the content is TRUE;
    # that's Canon/knowledge validators' job (a SEPARATE, still-active
    # check — see app.ai.validation.knowledge — not this one's).
    outcome = classify_relevance(
        "Qual o nome dessa vila?",
        "— Isto aqui é Vilarande — responde Perrin.",
        "Perrin Ferrow",
        context="CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\nName: Karvale",
    )

    assert outcome != RelevanceOutcome.NOT_ADDRESSED


# --- Case I: topic change makes the current question override the previous topic ---


def test_case_i_topic_change_is_judged_on_the_current_question_alone():
    # A prior exchange about the NPC's own identity must not leak into
    # how a brand new, differently-subjected question is judged.
    first = classify_relevance("Qual o seu nome?", "Meu nome é Perrin.", "Perrin Ferrow")
    assert first == RelevanceOutcome.ANSWERED

    second = classify_relevance(
        "E qual o nome dessa vila?",
        "— Isto é Karvale — responde Perrin.",
        "Perrin Ferrow",
        context="CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\nName: Karvale",
    )
    assert second == RelevanceOutcome.ANSWERED


# --- Case J: repeated generic service phrase on consecutive direct-question turns ---


class _NameLeakingLLM(LLMService):
    """Always tries to reveal the hidden location name, forcing the
    repair pipeline all the way to its final fallback branch — the
    worst case, where the model never self-corrects on revision."""

    def __init__(self, hidden_name: str) -> None:
        self.hidden_name = hidden_name
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return f"— Isto aqui é {self.hidden_name} — responde o interlocutor."


def test_transported_person_gets_an_honest_refusal_not_silence():
    # Found via the live 17-turn playtest: a transported simulated
    # player has no ambient local knowledge of the settlement's name
    # (unlike a resident NPC — see the ambient-local-knowledge exception
    # in narrator._find_hidden_name_violations) — the hidden-name guard
    # correctly blocks any attempt to reveal it. The fallback for this
    # exact case used to be blank scripted silence ("{name} permanece em
    # silêncio.") instead of an honest, in-character "I don't know" —
    # even though _find_canon_violations' own epistemic refusal already
    # existed for the conceptually identical "unsupported/unauthorized
    # world fact" case, just never wired up for hidden names specifically.
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\n"
        "Name: Quenhaven (HIDDEN — a private proper noun)\n\n"
        "PLAYER CURRENT LOCATION KNOWLEDGE\n"
        "Current location canonical name known to player: NO\n\n"
        "ACTIVE TRANSPORTED PERSON CONTEXT\nName: Corren Ashvale\n\n"
        "NPC KNOWLEDGE\n- none supplied"
    )

    result = narrator.narrate(
        _NameLeakingLLM("Quenhaven"),
        "Nenhuma mudança mecânica.",
        context,
        "Você sabe o nome dessa vila?",
        "(nenhuma troca anterior nesta cena)",
    )

    assert result != "Corren Ashvale permanece em silêncio."
    assert "Quenhaven" not in result


def test_case_j_repeated_generic_service_phrase_is_caught():
    context = "ACTIVE NPC CONTEXT\nName: Perrin Ferrow"
    history = 'Resposta de Perrin Ferrow anteriormente: "No momento não temos quartos disponíveis."'

    violations = narrator._find_stale_repeated_response_violations(
        "No momento não temos quartos disponíveis.",
        history,
        "Quanto custa um quarto para esta noite?",
    )

    assert violations
