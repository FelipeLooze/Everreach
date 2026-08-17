import random

from app.game import dice


def test_d20_within_bounds():
    rng = random.Random(42)
    for _ in range(200):
        result = dice.d20(modifier=3, rng=rng)
        assert 1 <= result.raw <= 20
        assert result.total == result.raw + 3


def test_roll_is_deterministic_with_seeded_rng():
    a = dice.roll(20, modifier=0, rng=random.Random(1))
    b = dice.roll(20, modifier=0, rng=random.Random(1))
    assert a.raw == b.raw
