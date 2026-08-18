from app.core.enums import NPCActivity
from app.simulation.npc_routines import activity_for_role


def test_blacksmith_works_during_day():
    assert activity_for_role("ferreiro", 10) == NPCActivity.WORKING


def test_blacksmith_is_available_after_work():
    assert activity_for_role("ferreiro", 19) == NPCActivity.AVAILABLE


def test_innkeeper_works_during_day():
    assert activity_for_role("estalajadeiro", 14) == NPCActivity.WORKING


def test_npc_rests_at_night():
    assert activity_for_role("ferreiro", 23) == NPCActivity.RESTING


def test_generic_role_is_available_during_day():
    assert activity_for_role("ancião", 12) == NPCActivity.AVAILABLE