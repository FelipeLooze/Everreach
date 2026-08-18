from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerSimulationResult:
    moved: int = 0
    trained: int = 0

    @property
    def total_changes(self) -> int:
        return self.moved + self.trained


@dataclass(frozen=True)
class NPCSimulationResult:
    changes: int = 0

@dataclass(frozen=True)
class WorldDevelopmentSimulationResult:
    changes: int = 0

@dataclass(frozen=True)
class WorldTickResult:
    simulated_player_moves: int = 0
    simulated_player_training: int = 0
    npc_changes: int = 0
    world_development_changes: int = 0

    @property
    def total_changes(self) -> int:
        return (
            self.simulated_player_moves
            + self.simulated_player_training
            + self.npc_changes
            + self.world_development_changes
        )

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0
