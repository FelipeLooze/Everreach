import random

from app.simulation import world_simulation
from app.simulation.results import (
    NPCSimulationResult,
    PlayerSimulationResult,
)

def test_world_tick_runs_subsystems_once_in_deterministic_order(
    db_session,
    monkeypatch,
):
    calls = []
    rng = random.Random(123)

    def fake_player_tick(
        db,
        campaign_id,
        minutes,
        rng=None,
    ):
        calls.append(
            (
                "players",
                campaign_id,
                minutes,
                rng,
            )
        )
        return PlayerSimulationResult(
            moved=2,
            trained=1,
        )

    def fake_npc_tick(
        db,
        campaign_id,
        minutes,
    ):
        calls.append(
            (
                "npcs",
                campaign_id,
                minutes,
            )
        )
        return NPCSimulationResult(
            changes=3,
        )

    monkeypatch.setattr(
        world_simulation.player_simulation,
        "tick",
        fake_player_tick,
    )

    monkeypatch.setattr(
        world_simulation.npc_simulation,
        "tick",
        fake_npc_tick,
    )

    result = world_simulation.tick(
        db_session,
        "campaign_1",
        45,
        rng=rng,
    )

    assert calls == [
        (
            "players",
            "campaign_1",
            45,
            rng,
        ),
        (
            "npcs",
            "campaign_1",
            45,
        ),
    ]
    assert result.simulated_player_moves == 2
    assert result.simulated_player_training == 1
    assert result.npc_changes == 3
    assert result.total_changes == 6
    assert result.has_changes is True


def test_world_tick_with_zero_minutes_runs_nothing(
    db_session,
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        world_simulation.player_simulation,
        "tick",
        lambda *args, **kwargs: calls.append("players"),
    )

    monkeypatch.setattr(
        world_simulation.npc_simulation,
        "tick",
        lambda *args, **kwargs: calls.append("npcs"),
    )

    result = world_simulation.tick(
        db_session,
        "campaign_1",
        0,
    )

    assert calls == []
    assert result.total_changes == 0
    assert result.has_changes is False


def test_world_tick_with_negative_minutes_runs_nothing(
    db_session,
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        world_simulation.player_simulation,
        "tick",
        lambda *args, **kwargs: calls.append("players"),
    )

    monkeypatch.setattr(
        world_simulation.npc_simulation,
        "tick",
        lambda *args, **kwargs: calls.append("npcs"),
    )

    result = world_simulation.tick(
        db_session,
        "campaign_1",
        -15,
    )

    assert calls == []
    assert result.total_changes == 0
    assert result.has_changes is False