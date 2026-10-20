"""Phase 24J.4 — Relational Canon, Factual Answers & Knowledge Acquisition.

Triggered directly by three defects the Phase 24J.3 report documented but
deliberately did not fix, given that phase's already-large scope:

1. route/direction relationships can be hallucinated by combining two real
   but unrelated facts (the inn's actual PATH-south connection and the
   Estrada do Moinho's actual ROAD-east connection get merged into "the inn
   is east, near Estrada do Moinho");
2. an NPC can falsely deny the existence of a real, locally-known service;
3. facts legitimately revealed in dialogue (e.g. the village's own name)
   were not reliably persisted as player knowledge.

Explicit architectural constraint from the governing spec: validate the
RELATIONSHIP between facts, not the vocabulary — the LLM keeps full freedom
over wording/tone/gestures/style.
"""

from app.ai.context_builder import fact_is_revealed_in_text
from app.ai.llm_service import LLMService
from app.ai.narrator import _find_canon_violations
from app.ai.validation import validate_narrative_proposal
from app.ai.validation.contract import NarrativeProposal
from app.ai.validation.relevance import RelevanceOutcome, classify_relevance
from app.core.enums import DiscoveryStatus, KnowerType
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import Location, LocationConnection
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.game_state import build_game_state
from app.game.npcs.service import KnownFact
from app.game.world.seed import create_campaign, grant_initial_player_knowledge, seed_initial_region


# --- Issue 1: Relational Geography Hallucination ---

_CONTEXT = (
    "CONNECTED LOCATIONS KNOWN TO PLAYER\n"
    "- sul -> Estalagem de Ulholt (trilha, distância 1)\n"
    "- leste -> Estrada do Moinho (estrada, distância 1)"
)


def test_case_a_merged_direction_and_route_is_rejected():
    # Inn south, Mill Road east. Claiming the inn is east via Mill Road
    # merges two real-but-unrelated connections.
    text = "A estalagem fica a leste, pela Estrada do Moinho."
    violations = _find_canon_violations(text, _CONTEXT, "Onde fica a estalagem?")
    assert violations


def test_case_b_correct_direction_for_the_inn_is_accepted():
    text = "A estalagem fica ao sul, pela trilha."
    violations = _find_canon_violations(text, _CONTEXT, "Onde fica a estalagem?")
    assert violations == []


def test_case_c_the_road_correctly_describing_itself_is_accepted():
    text = "A Estrada do Moinho sai da praça em direção leste."
    violations = _find_canon_violations(text, _CONTEXT, "Para onde vai a Estrada do Moinho?")
    assert violations == []


def test_case_d_two_correct_separate_claims_are_not_cross_contaminated():
    text = "A estalagem fica ao sul. A Estrada do Moinho fica a leste."
    violations = _find_canon_violations(text, _CONTEXT, "Onde ficam as coisas?")
    assert violations == []


_HIDDEN_NAME_CONTEXT = (
    "CONNECTED LOCATIONS KNOWN TO PLAYER\n"
    "- norte -> Local desconhecido [estalagem] (trilha, distância 1)\n"
    "- leste -> Local desconhecido [estrada] (estrada, distância 1)"
)


def test_hidden_destination_name_still_gets_validated_by_type():
    # Confirmed live: an early-game existence question is answered before
    # the player has been taught ANY destination's proper name — every
    # entry redacts to "Local desconhecido" in context, but the type
    # (visible via the square-bracket alias) is not secret and must still
    # ground the check.
    text = "A Estalagem de Wyngard é bem conhecida por aqui. Ela fica na parte leste da praça."
    violations = _find_canon_violations(text, _HIDDEN_NAME_CONTEXT, "Existe alguma estalagem aqui?")
    assert violations


def test_hidden_destination_name_correct_direction_is_accepted():
    text = "A Estalagem de Wyngard é bem conhecida por aqui. Ela fica na parte norte da praça."
    violations = _find_canon_violations(text, _HIDDEN_NAME_CONTEXT, "Existe alguma estalagem aqui?")
    assert violations == []


def test_cross_sentence_pronoun_reference_carries_the_destination_forward():
    # The SAME split-sentence shape as the live failure, but with the
    # proper noun already known — the direction claim in the SECOND
    # sentence has no destination mention of its own ("Ela fica..."),
    # only a pronoun referring back to the first sentence's subject.
    # _CONTEXT's estalagem is south; its road is east.
    text = "A estalagem é bem conhecida por aqui. Ela fica ao sul."
    violations = _find_canon_violations(text, _CONTEXT, "Onde fica a estalagem?")
    assert violations == []

    wrong_text = "A estalagem é bem conhecida por aqui. Ela fica a leste."
    violations = _find_canon_violations(wrong_text, _CONTEXT, "Onde fica a estalagem?")
    assert violations


def test_direction_question_grounding_gives_the_real_connection(db_session):
    # Confirmed live: "Onde fica a ferraria?" is a SERVICE-subject,
    # non-existence question with no grounding branch of its own — when
    # the conversational-relevance repair path kicked in for an UNRELATED
    # reason, the model had no authorized fact and invented BOTH a wrong
    # direction and fabricated street names ("Rua dos Ferreiros"),
    # entirely unchecked (that repair candidate is only re-validated for
    # hidden names and relevance, never canon/geography).
    from app.ai.context_builder import build_context
    from app.game.character.service import create_character
    from app.game.game_state import build_game_state
    from app.game.world.seed import create_campaign, seed_initial_region

    campaign = create_campaign(db_session, "24J4 Direction Grounding")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.commit()
    elder = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.role == "ancião da vila").one()
    blacksmith_connection = (
        db_session.query(LocationConnection)
        .join(Location, Location.id == LocationConnection.to_location_id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "blacksmith")
        .first()
    )

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state, active_interlocutor=elder.id, player_input="Onde fica a ferraria?")

    assert "DIRECT QUESTION GROUNDING" in context
    section = context.split("DIRECT QUESTION GROUNDING", 1)[1].split("\n\n")[0]
    assert blacksmith_connection.direction in section


def test_the_exact_confirmed_live_failure_text_is_rejected():
    text = "A Estalagem de Ulholt fica na parte leste da vila, perto da Estrada do Moinho."
    violations = _find_canon_violations(text, _CONTEXT, "Onde fica a estalagem?")
    assert any("Estalagem de Ulholt" in v for v in violations)


def test_a_direction_with_no_known_destination_nearby_does_not_false_positive():
    # Generic direction talk unrelated to any known destination must not be
    # flagged — the validator only fires when it can correlate a claim to a
    # SPECIFIC destination's own connection.
    text = "O sol nasce a leste todos os dias."
    violations = _find_canon_violations(text, _CONTEXT, "Como é o clima?")
    assert violations == []


def test_generic_service_alias_alone_still_resolves_correctly():
    # "a estalagem" (the generic Portuguese service label, not the full
    # proper name) must still correlate to the correct connection.
    text = "A estalagem fica ao sul da praça."
    violations = _find_canon_violations(text, _CONTEXT, "Onde fica a estalagem?")
    assert violations == []


def test_no_known_connections_in_context_never_crashes_or_false_positives():
    violations = _find_canon_violations(
        "A estalagem fica a leste.", "CANONICAL LOCATION CONTEXT\nName: Ulholt", "Onde fica?"
    )
    # No structured connection data available — the coarse existing check
    # may or may not fire, but the new destination-specific check must not
    # crash on absent data.
    assert isinstance(violations, list)


# --- Issue 2: False Factual Denial ---


def _service_scene(db_session):
    campaign = create_campaign(db_session, "24J4 Service Existence")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    db_session.commit()
    elder = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.role == "ancião da vila").one()
    shop = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == village.id, Location.type == "shop")
        .first()
    )
    return campaign, character, village, elder, shop


def test_confident_denial_of_a_real_service_is_rejected(db_session):
    campaign, character, village, elder, shop = _service_scene(db_session)
    assert shop is not None

    proposal = NarrativeProposal(
        text="Não há nenhuma loja geral propriamente dita aqui.",
        mode="CONTINUATION",
        context="CANONICAL LOCATION CONTEXT",
        mechanical_summary="",
        player_input="Existe alguma loja geral na vila?",
        recent_history="",
        character_name=character.name,
        character_id=character.id,
        location_id=village.id,
        active_npc_id=elder.id,
        active_npc_name=elder.name,
    )
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is False


def test_honest_ignorance_about_a_real_service_is_not_flagged(db_session):
    # "I don't know whether there is one" is a legitimate answer per the
    # spec — the validator must never coerce a confident answer out of
    # genuine uncertainty.
    campaign, character, village, elder, shop = _service_scene(db_session)
    assert shop is not None

    proposal = NarrativeProposal(
        text="Não sei dizer ao certo se há uma loja geral por aqui.",
        mode="CONTINUATION",
        context="CANONICAL LOCATION CONTEXT",
        mechanical_summary="",
        player_input="Existe alguma loja geral na vila?",
        recent_history="",
        character_name=character.name,
        character_id=character.id,
        location_id=village.id,
        active_npc_id=elder.id,
        active_npc_name=elder.name,
    )
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is True


def test_denial_from_a_non_resident_npc_is_not_flagged(db_session):
    # KNOWLEDGE and TRUTH stay separate: an NPC never established as a
    # local resident isn't treated as authoritatively knowledgeable about
    # the settlement's own services — a wrong denial from them is a more
    # defensible "genuinely doesn't know," not a generation error.
    campaign, character, village, elder, shop = _service_scene(db_session)
    assert shop is not None

    proposal = NarrativeProposal(
        text="Não há nenhuma loja geral por aqui.",
        mode="CONTINUATION",
        context="CANONICAL LOCATION CONTEXT",
        mechanical_summary="",
        player_input="Existe alguma loja geral na vila?",
        recent_history="",
        character_name=character.name,
        character_id=character.id,
        location_id=village.id,
        active_npc_id=None,
        active_npc_name=None,
    )
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is True


def test_denial_of_a_nonexistent_service_is_not_flagged(db_session):
    campaign, character, village, elder, shop = _service_scene(db_session)

    proposal = NarrativeProposal(
        text="Não há nenhum templo por aqui.",
        mode="CONTINUATION",
        context="CANONICAL LOCATION CONTEXT",
        mechanical_summary="",
        player_input="Existe algum templo na vila?",
        recent_history="",
        character_name=character.name,
        character_id=character.id,
        location_id=village.id,
        active_npc_id=elder.id,
        active_npc_name=elder.name,
    )
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is True


class _ExistenceDenialThenCorrectionLLM(LLMService):
    """First draft falsely denies; on the targeted-repair call, confirms."""

    def __init__(self, elder_name: str, shop_name: str) -> None:
        self.calls: list[tuple[str, str]] = []
        self._elder_name = elder_name
        self._shop_name = shop_name

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            return f'{{"intent": "TALK", "target": "{self._elder_name}"}}'
        if "negou isso com confiança" in prompt or "Fato autorizado" in prompt:
            return f"— Sim, {self._shop_name} existe — responde {self._elder_name}."
        return f"— Não há nenhuma loja geral aqui — responde {self._elder_name}."


def test_manual_review_preserves_first_narrative_draft(client, db_session):
    from app.api.dependencies.llm import set_llm_service_override

    campaign_resp = client.post("/api/campaigns", json={"name": "24J4 Existence Sequential"})
    campaign_id = campaign_resp.json()["id"]
    character_resp = client.post(
        f"/api/campaigns/{campaign_id}/characters", json={"name": "Logan"}
    )
    character_id = character_resp.json()["id"]
    start_resp = client.post(f"/api/campaigns/{campaign_id}/start?character_id={character_id}")
    elder = next(
        npc for npc in start_resp.json()["state"]["nearby_npcs"] if npc["role"] == "ancião da vila"
    )

    stub_llm = _ExistenceDenialThenCorrectionLLM(elder["name"], "Loja Geral")
    set_llm_service_override(stub_llm)
    try:
        talk_resp = client.post(
            f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
            json={"text": f'Logan vai falar com {elder["name"]} "Existe alguma loja geral na vila?"'},
        )
        assert talk_resp.status_code == 200
        narrative = talk_resp.json()["narrative"]
        assert "não há" in narrative.casefold()
        # One intent call plus one narration call; there is no automatic
        # correction call. The player may request regeneration explicitly.
        assert len(stub_llm.calls) == 2
    finally:
        set_llm_service_override(None)


# --- Issue 3: Dialogue-Revealed Knowledge ---


def _cardal_scene(db_session):
    campaign = create_campaign(db_session, "24J4 Dialogue Knowledge")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    grant_initial_player_knowledge(db_session, campaign.id, character.id)
    db_session.commit()
    elder = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.role == "ancião da vila").one()
    return campaign, character, village, region, elder


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


def test_partial_reveal_of_only_the_village_name_is_taught(db_session):
    # The confirmed live bug: an elder said ONLY the village name, without
    # the exact region phrase — previously this taught NOTHING, because
    # _proper_nouns silently required the region's words too (they led
    # the OTHER half of the bundled fact, not this one). Now split into
    # independent facts, a partial reveal teaches exactly what was said.
    fact = KnownFact(
        subject="location:village_1",
        fact_key="settlement_name_known",
        statement="Esta vila se chama Elhelm.",
        source="local",
        certainty="CONFIRMED",
        discovered_at=None,
    )
    assert fact_is_revealed_in_text(fact, "Esta é Elhelm, jovem estrangeiro.")


class _NameThenLaterReferenceLLM(LLMService):
    def __init__(self, elder_name: str, village_name: str) -> None:
        self.calls: list[tuple[str, str]] = []
        self._elder_name = elder_name
        self._village_name = village_name
        self._n = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            return f'{{"intent": "TALK", "target": "{self._elder_name}"}}'
        self._n += 1
        if self._n == 1:
            return f"— Isto aqui é {self._village_name}, jovem — responde {self._elder_name}."
        return f"— Sim, {self._village_name} é uma vila tranquila — responde {self._elder_name}."


def test_sequential_production_path_name_reveal_persists_to_the_next_turn(client, db_session):
    from app.api.dependencies.llm import set_llm_service_override
    from app.db.models.location import Location as LocationModel

    campaign_resp = client.post("/api/campaigns", json={"name": "24J4 Knowledge Sequential"})
    campaign_id = campaign_resp.json()["id"]
    character_resp = client.post(
        f"/api/campaigns/{campaign_id}/characters", json={"name": "Logan"}
    )
    character_id = character_resp.json()["id"]
    start_resp = client.post(f"/api/campaigns/{campaign_id}/start?character_id={character_id}")
    elder = next(
        npc for npc in start_resp.json()["state"]["nearby_npcs"] if npc["role"] == "ancião da vila"
    )
    village_id = start_resp.json()["state"]["character"]["location_id"]
    village = db_session.get(LocationModel, village_id)

    stub_llm = _NameThenLaterReferenceLLM(elder["name"], village.name)
    set_llm_service_override(stub_llm)
    try:
        turn1 = client.post(
            f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
            json={"text": f'Logan vai falar com {elder["name"]} "Qual o nome dessa vila?"'},
        )
        assert turn1.status_code == 200
        assert village.name in turn1.json()["narrative"]

        # TURN N+1: the fact must already be player knowledge on the very
        # next action, without any further teaching step.
        fact_keys = _player_fact_keys(db_session, character_id)
        assert "settlement_name_known" in fact_keys

        turn2 = client.post(
            f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
            json={"text": '"Voltei! Pode confirmar o nome da vila de novo?"'},
        )
        assert turn2.status_code == 200
        assert village.name in turn2.json()["narrative"]
    finally:
        set_llm_service_override(None)


class _AgencyViolatingRevealLLM(LLMService):
    """Voices the real village name, but ALWAYS as a protagonist-agency
    violation ("Hero sorri...") — every attempt, including revisions —
    forcing the pipeline all the way to the safe fallback."""

    def __init__(self, elder_name: str, village_name: str, character_name: str) -> None:
        self.calls: list[tuple[str, str]] = []
        self._elder_name = elder_name
        self._village_name = village_name
        self._character_name = character_name

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            return f'{{"intent": "TALK", "target": "{self._elder_name}"}}'
        # The reveal and the violation are entangled in ONE sentence, so
        # the pipeline's own granular (sentence-level) trim repair cannot
        # keep the name while dropping only the violating clause — it
        # must drop the whole sentence, taking the reveal down with it.
        return (
            f"{self._character_name} descobre, satisfeito, que esta vila se chama "
            f"{self._village_name} e decide confiar em {self._elder_name}."
        )


def test_a_reveal_inside_a_rejected_draft_is_not_taught(client, db_session, monkeypatch):
    from app.api.dependencies.llm import set_llm_service_override
    from app.core.config import Settings
    from app.db.models.location import Location as LocationModel

    # This regression specifically verifies the opt-in automatic agency
    # guard. Keep it explicit so a developer's local manual-review setting
    # cannot silently change what this test exercises.
    monkeypatch.setattr(
        engine,
        "get_settings",
        lambda: Settings(
            narrative_player_agency_guard_enabled=True,
            narrative_automatic_validation_enabled=True,
        ),
    )

    campaign_resp = client.post("/api/campaigns", json={"name": "24J4 Rejected Reveal"})
    campaign_id = campaign_resp.json()["id"]
    character_resp = client.post(
        f"/api/campaigns/{campaign_id}/characters", json={"name": "Logan"}
    )
    character_id = character_resp.json()["id"]
    start_resp = client.post(f"/api/campaigns/{campaign_id}/start?character_id={character_id}")
    elder = next(
        npc for npc in start_resp.json()["state"]["nearby_npcs"] if npc["role"] == "ancião da vila"
    )
    village_id = start_resp.json()["state"]["character"]["location_id"]
    village = db_session.get(LocationModel, village_id)

    stub_llm = _AgencyViolatingRevealLLM(elder["name"], village.name, "Logan")
    set_llm_service_override(stub_llm)
    try:
        resp = client.post(
            f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
            json={"text": f'Logan vai falar com {elder["name"]} "Qual o nome dessa vila?"'},
        )
        assert resp.status_code == 200
        # The agency-violating draft never survives to the player...
        assert village.name not in resp.json()["narrative"]
        # ...and because it never appears in the FINAL text, it must not
        # have been taught either — this is the actual guarantee (a name
        # that never reached the player must never become known).
        fact_keys = _player_fact_keys(db_session, character_id)
        assert "settlement_name_known" not in fact_keys
    finally:
        set_llm_service_override(None)
