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