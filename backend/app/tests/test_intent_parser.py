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
    assert decoded[5:] == ("espada", "MELEE_ATTACK", "SLASH", "TORSO")
