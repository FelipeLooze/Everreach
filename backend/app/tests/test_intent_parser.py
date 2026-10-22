from app.ai.intent_parser import _parse_response
from app.core.enums import ActionIntentType, TravelPace


def test_parse_move_pace_fast():
    intent_type, target, pace = _parse_response(
        '{"intent":"MOVE","target":"Bosque","pace":"FAST"}'
    )

    assert intent_type == ActionIntentType.MOVE
    assert target == "Bosque"
    assert pace == TravelPace.FAST


def test_parse_move_pace_slow():
    intent_type, target, pace = _parse_response(
        '{"intent":"MOVE","target":"Bosque","pace":"SLOW"}'
    )

    assert intent_type == ActionIntentType.MOVE
    assert target == "Bosque"
    assert pace == TravelPace.SLOW


def test_parse_missing_pace_defaults_to_normal():
    intent_type, target, pace = _parse_response(
        '{"intent":"MOVE","target":"Bosque"}'
    )

    assert intent_type == ActionIntentType.MOVE
    assert target == "Bosque"
    assert pace == TravelPace.NORMAL


def test_parse_invalid_pace_defaults_to_normal():
    intent_type, target, pace = _parse_response(
        '{"intent":"MOVE","target":"Bosque","pace":"SUPER_FAST"}'
    )

    assert intent_type == ActionIntentType.MOVE
    assert pace == TravelPace.NORMAL


def test_parse_accept_quest_keeps_player_facing_title_as_target():
    intent_type, target, pace = _parse_response(
        '{"intent":"ACCEPT_QUEST","target":"Relato da Primeira Chegada"}'
    )

    assert intent_type == ActionIntentType.ACCEPT_QUEST
    assert target == "Relato da Primeira Chegada"
    assert pace == TravelPace.NORMAL


def test_parse_combat_details_without_granting_outcome_authority():
    from app.ai.intent_parser import _decode_response

    decoded = _decode_response(
        '{"intent":"ATTACK","target":"bandido","weapon":"espada",'
        '"attack_type":"MELEE_ATTACK","damage_profile":"SLASH",'
        '"body_area":"TORSO","pace":"NORMAL"}'
    )

    assert decoded[0] == ActionIntentType.ATTACK
    assert decoded[1] == "bandido"
    assert decoded[5:9] == ("espada", "MELEE_ATTACK", "SLASH", "TORSO")
    assert decoded[9:] == (None, None, None)


def test_parse_experiment_pattern_and_domains():
    from app.ai.intent_parser import _decode_response

    decoded = _decode_response(
        '{"intent":"EXPERIMENT","pattern_key":"wind-palm-compress",'
        '"domains":"WIND","technique_type":"MAGICAL","pace":"NORMAL"}'
    )

    assert decoded[0] == ActionIntentType.EXPERIMENT
    assert decoded[9:] == ("wind-palm-compress", "WIND", "MAGICAL")


def test_truncated_json_salvages_the_explicit_intent():
    # Groq may exhaust its output budget after already emitting the fields we
    # need. A broken JSON tail must not erase an explicit EXAMINE classification.
    intent_type, target, pace = _parse_response(
        '{"intent":"EXAMINE","target":null,"secondary_target":null,"damage'
    )

    assert intent_type == ActionIntentType.EXAMINE
    assert target is None
    assert pace == TravelPace.NORMAL


def test_truncated_json_salvages_a_complete_literal_target():
    intent_type, target, pace = _parse_response(
        '{"intent":"TALK","target":"homem idoso","secondary_target"'
    )

    assert intent_type == ActionIntentType.TALK
    assert target == "homem idoso"
    assert pace == TravelPace.NORMAL


class _ScriptedLLM:
    """Raises/returns each scripted step in turn; records the call count."""

    def __init__(self, *steps):
        from app.ai.llm_service import LLMService

        class _Service(LLMService):
            calls = 0
            last_generation_metadata = None

            def generate(inner, system, prompt):
                inner.calls += 1
                step = steps[inner.calls - 1]
                if isinstance(step, Exception):
                    raise step
                return step

        self.service = _Service()


_TALK_JSON = '{"intent": "TALK", "target": null}'


def test_intent_parser_retries_once_after_a_short_rate_limit(monkeypatch):
    # Playtest: back-to-back turns hit Groq's 8k tokens/minute with a
    # "try again in 5s" and every one of them fell straight to FREEFORM.
    from app.ai import intent_parser
    from app.ai.llm_service import LLMRateLimitError

    sleeps = []
    monkeypatch.setattr(intent_parser.time, "sleep", sleeps.append)
    llm = _ScriptedLLM(LLMRateLimitError("rate limited", retry_after_seconds=5.13), _TALK_JSON)

    intent = intent_parser.parse(llm.service, "Falo com o ancião.", "")

    assert intent.type == ActionIntentType.TALK
    assert llm.service.calls == 2
    assert sleeps and 5.13 <= sleeps[0] < 6


def test_intent_parser_retries_once_after_an_empty_completion(monkeypatch):
    from app.ai import intent_parser
    from app.ai.llm_service import LLMEmptyCompletionError

    monkeypatch.setattr(intent_parser.time, "sleep", lambda _seconds: None)
    llm = _ScriptedLLM(LLMEmptyCompletionError("empty"), _TALK_JSON)

    assert intent_parser.parse(llm.service, "Falo com o ancião.", "").type == ActionIntentType.TALK
    assert llm.service.calls == 2


def test_intent_parser_does_not_wait_out_a_long_rate_limit(monkeypatch):
    from app.ai import intent_parser
    from app.ai.llm_service import LLMRateLimitError

    sleeps = []
    monkeypatch.setattr(intent_parser.time, "sleep", sleeps.append)
    llm = _ScriptedLLM(LLMRateLimitError("daily quota", retry_after_seconds=3600))

    intent = intent_parser.parse(llm.service, "Falo com o ancião.", "")

    assert intent.type == ActionIntentType.FREEFORM
    assert llm.service.calls == 1
    assert sleeps == []
