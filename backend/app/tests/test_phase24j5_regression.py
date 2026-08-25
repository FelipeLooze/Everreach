"""Phase 24J.5 — Final Known-Gap Cleanup Before Human Playtest.

Closes exactly the three real defects the Phase 24J.4 report documented:

1. false "service is in the central square" containment claims;
2. an opening-interaction hard fallback whose FALLBACK TEXT (not the guard
   itself) was wrong for the mode;
3. a "look around" hard fallback after farewell, caused by the player-
   agency guard having no exception for perception-framing verbs the
   model naturally reaches for ("dá uma volta de olhos") even though this
   turn's own authoritative mechanical fact confirms it was an
   authorized observation action.
"""

from app.ai.llm_service import LLMService
from app.ai.narrator import (
    _containment_violations_in_segment,
    _find_canon_violations,
    _normalized,
    _parse_known_connections,
    _protagonist_agency_violations,
    _relational_geography_violations_in_segment,
)


# --- Issue 1: False Containment / Same-Location Claim ---

_CONTEXT = (
    "CONNECTED LOCATIONS KNOWN TO PLAYER\n"
    "- oeste -> Local desconhecido [loja geral] (trilha, distância 1)\n\n"
    "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\n"
    "Name: Wyngard\nType: VILLAGE\nRegion: Terras Altas de Sernn"
)


def test_case_a_containment_claim_for_a_separate_location_is_rejected():
    # Confirmed live: "Você pode encontrá-la na praça central, bem no
    # coração da vila" for a shop that is actually a separate connected
    # Location — a spatial factual error even with no wrong direction.
    text = "Sim, a Loja Geral existe. Você pode encontrá-la na praça central, bem no coração da vila."
    violations = _find_canon_violations(text, _CONTEXT, "Existe uma loja geral?")
    assert any("local atual" in v for v in violations)


def test_case_b_correct_direction_reference_to_the_square_is_accepted():
    text = "A loja fica a oeste, na parte norte da praça, por uma trilha."
    conns = _parse_known_connections(_CONTEXT)
    violations = _containment_violations_in_segment(_normalized(text), conns)
    assert violations == []


def test_case_c_loose_nearby_wording_is_never_rejected():
    text = "A loja fica perto daqui."
    violations = _find_canon_violations(text, _CONTEXT, "Onde fica a loja?")
    assert not any("local atual" in v for v in violations)


def test_explicit_same_segment_containment_is_rejected():
    conns = _parse_known_connections(_CONTEXT)
    text = _normalized("A Loja Geral fica na praça central.")
    violations = _containment_violations_in_segment(text, conns)
    assert violations


def test_relative_direction_phrase_naming_the_square_is_not_containment():
    # The exact false-positive a first version of this check produced:
    # "fica NA PARTE norte DA praça" contains "fica", "na", and "praça"
    # somewhere in the sentence, but "na" and "praça" are not adjacent —
    # this is a legitimate relative-direction phrase, not a containment
    # claim, and the existing direction check already accepts it.
    conns = _parse_known_connections(_CONTEXT)
    text = _normalized("Ela fica na parte norte da praça.")
    violations = _containment_violations_in_segment(text, conns)
    assert violations == []


def test_pronoun_containment_claim_carries_forward_across_sentences():
    # The confirmed live shape: the destination is named in one sentence,
    # the containment claim follows in the next via a bare pronoun.
    conns = _parse_known_connections(_CONTEXT)
    first = _normalized("A Loja Geral existe.")
    second = _normalized("Você pode encontrá-la na praça central.")
    _v1, carried = _relational_geography_violations_in_segment(first, conns, None)
    v2 = _containment_violations_in_segment(second, conns, carried)
    assert v2


# --- Issue 2: Opening-Interaction Hard Fallback ---


def test_opening_fallback_is_not_the_nonsensical_generic_line():
    from app.ai.narrator import _safe_hard_failure_fallback

    result = _safe_hard_failure_fallback("OPENING")
    assert result != "Nada acontece de imediato."
    assert "Logan" in result or "mundo" in result


def test_continuation_fallback_with_no_npc_is_unchanged():
    from app.ai.narrator import _safe_hard_failure_fallback

    assert _safe_hard_failure_fallback("CONTINUATION") == "Nada acontece de imediato."


def test_continuation_fallback_with_npc_is_unchanged():
    from app.ai.narrator import _safe_hard_failure_fallback

    assert _safe_hard_failure_fallback("CONTINUATION", "Aldric") == "Aldric permanece em silêncio."


class _StubbornOpeningApproachLLM(LLMService):
    """The confirmed live shape: the model insists an NPC 'se aproxima'
    during the opening, across every revision attempt."""

    def generate(self, system: str, prompt: str) -> str:
        return (
            "Logan se encontra subitamente em uma praça desgastada. Aldric, o ancião da vila, "
            "se aproxima lentamente, parecendo intrigado com os acontecimentos."
        )


def test_stubborn_opening_approach_falls_to_the_opening_fallback_not_generic():
    from app.ai import narrator

    llm = _StubbornOpeningApproachLLM()
    context = (
        "CURRENT PLAYER\nName: Logan\n\n"
        "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\nName: Cardal\nType: VILLAGE\n\n"
        "VISIBLE NPCS\n- Aldric (ancião; activity=IDLE)\n\n"
        "ACTIVE NPC CONTEXT\n- none"
    )
    result = narrator.narrate(
        llm,
        "Logan está fisicamente presente no ponto inicial após o transporte.",
        context,
        "(nenhuma ação do jogador; abertura da campanha)",
        "(nenhum histórico)",
        mode="OPENING",
    )
    assert result != "Nada acontece de imediato."
    assert "se aproxima" not in result.casefold()


# --- Issue 3: Look-Around Hard Fallback After Farewell ---


def test_observation_framing_verb_allowed_only_when_backend_confirms_observation():
    text = (
        "Logan dá uma última volta de olhos pela vila, avaliando seus arredores antes de "
        "prosseguir com suas próximas ações."
    )
    assert _protagonist_agency_violations(text, "Logan", "CONTINUATION") != []
    assert (
        _protagonist_agency_violations(text, "Logan", "CONTINUATION", is_observation_turn=True)
        == []
    )


def test_invented_decision_still_blocked_even_during_an_observation_turn():
    # The gating must not become a general loophole for agency violations
    # merely because this turn happens to be an EXAMINE.
    text = "Logan decide roubar a bolsa do estalajadeiro."
    assert (
        _protagonist_agency_violations(text, "Logan", "CONTINUATION", is_observation_turn=True)
        != []
    )


class _ObservationFramingLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        if "intent" in system.lower():
            return '{"intent": "EXAMINE", "target": null}'
        return (
            "Logan dá uma última volta de olhos ao redor, avaliando os arredores com atenção "
            "antes de prosseguir."
        )


def test_sequential_production_path_observation_after_farewell_is_not_blocked(client, db_session):
    # Confirmed live shape: farewell an NPC, then "olhar ao redor" — the
    # observation narration must not fall to a hard agency fallback.
    from app.api.dependencies.llm import set_llm_service_override

    campaign_resp = client.post("/api/campaigns", json={"name": "24J5 Observation Sequential"})
    campaign_id = campaign_resp.json()["id"]
    character_resp = client.post(
        f"/api/campaigns/{campaign_id}/characters", json={"name": "Logan"}
    )
    character_id = character_resp.json()["id"]
    client.post(f"/api/campaigns/{campaign_id}/start?character_id={character_id}")

    stub_llm = _ObservationFramingLLM()
    set_llm_service_override(stub_llm)
    try:
        resp = client.post(
            f"/api/campaigns/{campaign_id}/actions?character_id={character_id}",
            json={"text": "Logan olha ao redor mais uma vez"},
        )
        assert resp.status_code == 200
        narrative = resp.json()["narrative"]
        assert narrative != "Nada acontece de imediato."
        assert "permanece em silêncio" not in narrative
    finally:
        set_llm_service_override(None)


# --- Issues D/E: opening → ordinary gameplay transition ---


def test_mode_defaults_to_continuation_for_every_ordinary_action(client, db_session):
    # The opening→continuation transition is architecturally guaranteed:
    # mode="OPENING" is only ever passed once, from the /start route
    # itself (app/api/routes/campaigns.py) — every /actions call always
    # narrates in CONTINUATION mode, regardless of anything else. This
    # test documents/locks in that guarantee rather than re-discovering it.
    import inspect

    from app.game import engine

    source = inspect.getsource(engine.resolve_action)
    assert 'mode="OPENING"' not in source
    assert "mode='OPENING'" not in source
