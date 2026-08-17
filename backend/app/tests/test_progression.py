from app.db.models.character import Character
from app.game.progression.service import add_xp, xp_to_next_level


def test_xp_requirement_grows_with_level():
    assert xp_to_next_level(1) > xp_to_next_level(0)
    assert xp_to_next_level(10) > xp_to_next_level(5)


def test_add_xp_below_threshold_does_not_level_up():
    character = Character(name="Test", level=0, xp=0)
    levels_gained = add_xp(character, 1)
    assert levels_gained == 0
    assert character.level == 0
    assert character.xp == 1


def test_add_xp_levels_up_and_carries_remainder():
    character = Character(name="Test", level=0, xp=0)
    needed = xp_to_next_level(0)
    levels_gained = add_xp(character, needed + 5)
    assert levels_gained == 1
    assert character.level == 1
    assert character.xp == 5


def test_add_xp_can_grant_multiple_levels_at_once():
    character = Character(name="Test", level=0, xp=0)
    huge_amount = xp_to_next_level(0) + xp_to_next_level(1) + 1
    levels_gained = add_xp(character, huge_amount)
    assert levels_gained == 2
    assert character.level == 2
