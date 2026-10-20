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
