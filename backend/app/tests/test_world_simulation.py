import random

from app.simulation import world_simulation
from app.simulation.results import (
    KnowledgeSimulationResult,
    NPCSimulationResult,
    PlayerSimulationResult,
    SimulatedPlayerArrivalSimulationResult,
    SimulatedPlayerGroupSimulationResult,
    WorldDevelopmentSimulationResult,
)


def test_world_tick_runs_subsystems_once_in_deterministic_order(
    db_session,
    monkeypatch,
):
    calls = []

    def fake_arrival_tick(
        db,
        campaign_id,
        minutes,
    ):
        calls.append(
            (
                "arrivals",
                campaign_id,
                minutes,
            )
        )

        return SimulatedPlayerArrivalSimulationResult(
            arrivals=1,
        )

    rng = random.Random(123)

    def fake_group_tick(db, campaign_id, minutes):
        calls.append(("groups", campaign_id, minutes))
        return SimulatedPlayerGroupSimulationResult()

    def fake_player_tick(
        db,
        campaign_id,
        minutes,
        rng=None,
        scope=None,
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
        scope=None,
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

    def fake_development_tick(
        db,
        campaign_id,
        minutes,
    ):
        calls.append(
            (
                "developments",
                campaign_id,
                minutes,
            )
        )
        return WorldDevelopmentSimulationResult(
            changes=4,
        )

    def fake_knowledge_tick(
        db,
        campaign_id,
        minutes,
        scope=None,
    ):
        calls.append(
            (
                "knowledge",
                campaign_id,
                minutes,
            )
        )
        return KnowledgeSimulationResult(
            opportunities=5,
            propagations=6,
        )

    monkeypatch.setattr(
        world_simulation.arrival_simulation,
        "tick",
        fake_arrival_tick,
    )

    monkeypatch.setattr(
        world_simulation.player_simulation,
        "tick",
        fake_player_tick,
    )
    monkeypatch.setattr(
        world_simulation.group_simulation,
        "tick",
        fake_group_tick,
    )

    monkeypatch.setattr(
        world_simulation.npc_simulation,
        "tick",
        fake_npc_tick,
    )

    monkeypatch.setattr(
        world_simulation.development_simulation,
        "tick",
        fake_development_tick,
    )

    monkeypatch.setattr(
        world_simulation.knowledge_simulation,
        "tick",
        fake_knowledge_tick,
    )

    result = world_simulation.tick(
        db_session,
        "campaign_1",
        45,
        rng=rng,
    )

    assert calls == [
        (
            "arrivals",
            "campaign_1",
            45,
        ),
        ("groups", "campaign_1", 45),
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
        (
            "developments",
            "campaign_1",
            45,
        ),
        (
            "knowledge",
            "campaign_1",
            45,
        ),
    ]

    assert result.simulated_player_moves == 2
    assert result.simulated_player_training == 1
    assert result.npc_changes == 3
    assert result.world_development_changes == 4

    assert (
        result.knowledge_social_opportunities
        == 5
    )

    assert result.knowledge_propagations == 6
    assert result.simulated_player_arrivals == 1
    assert result.total_changes == 17
    assert result.has_changes is True


def test_knowledge_opportunity_does_not_count_as_world_change(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        world_simulation.arrival_simulation,
        "tick",
        lambda *args, **kwargs: (
            SimulatedPlayerArrivalSimulationResult()
        ),
    )
    
    monkeypatch.setattr(
        world_simulation.player_simulation,
        "tick",
        lambda *args, **kwargs: PlayerSimulationResult(),
    )
    monkeypatch.setattr(
        world_simulation.group_simulation,
        "tick",
        lambda *args, **kwargs: SimulatedPlayerGroupSimulationResult(),
    )

    monkeypatch.setattr(
        world_simulation.npc_simulation,
        "tick",
        lambda *args, **kwargs: NPCSimulationResult(),
    )

    monkeypatch.setattr(
        world_simulation.development_simulation,
        "tick",
        lambda *args, **kwargs: (
            WorldDevelopmentSimulationResult()
        ),
    )

    monkeypatch.setattr(
        world_simulation.knowledge_simulation,
        "tick",
        lambda *args, **kwargs: (
            KnowledgeSimulationResult(
                opportunities=1,
                propagations=0,
            )
        ),
    )

    result = world_simulation.tick(
        db_session,
        "campaign_1",
        60,
    )

    assert (
        result.knowledge_social_opportunities
        == 1
    )

    assert result.knowledge_propagations == 0
    assert result.total_changes == 0
    assert result.has_changes is False


def test_world_tick_with_zero_minutes_runs_nothing(
    db_session,
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        world_simulation.player_simulation,
        "tick",
        lambda *args, **kwargs: calls.append(
            "players"
        ),
    )

    monkeypatch.setattr(
        world_simulation.npc_simulation,
        "tick",
        lambda *args, **kwargs: calls.append(
            "npcs"
        ),
    )

    monkeypatch.setattr(
        world_simulation.development_simulation,
        "tick",
        lambda *args, **kwargs: calls.append(
            "developments"
        ),
    )

    monkeypatch.setattr(
        world_simulation.knowledge_simulation,
        "tick",
        lambda *args, **kwargs: calls.append(
            "knowledge"
        ),
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
        lambda *args, **kwargs: calls.append(
            "players"
        ),
    )

    monkeypatch.setattr(
        world_simulation.npc_simulation,
        "tick",
        lambda *args, **kwargs: calls.append(
            "npcs"
        ),
    )

    monkeypatch.setattr(
        world_simulation.development_simulation,
        "tick",
        lambda *args, **kwargs: calls.append(
            "developments"
        ),
    )

    monkeypatch.setattr(
        world_simulation.knowledge_simulation,
        "tick",
        lambda *args, **kwargs: calls.append(
            "knowledge"
        ),
    )

    result = world_simulation.tick(
        db_session,
        "campaign_1",
        -15,
    )

    assert calls == []
    assert result.total_changes == 0
    assert result.has_changes is False
