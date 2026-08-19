from app.core.enums import SimulatedPlayerActivity
from app.db.models.simulated_player import SimulatedPlayer


def test_simulated_player_activity_states_are_defined():
    assert SimulatedPlayerActivity.AVAILABLE == "AVAILABLE"
    assert SimulatedPlayerActivity.RESTING == "RESTING"
    assert SimulatedPlayerActivity.TRAINING == "TRAINING"
    assert SimulatedPlayerActivity.SOCIALIZING == "SOCIALIZING"
    assert SimulatedPlayerActivity.WORKING == "WORKING"


def test_simulated_player_activity_defaults_to_available():
    column = SimulatedPlayer.__table__.c.activity

    assert column.nullable is False
    assert column.default is not None
    assert (
        column.default.arg
        == SimulatedPlayerActivity.AVAILABLE
    )