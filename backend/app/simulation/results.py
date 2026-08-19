from dataclasses import dataclass


@dataclass(frozen=True)
class SimulatedPlayerArrivalSimulationResult:
    arrivals: int = 0

@dataclass(frozen=True)
class PlayerSimulationResult:
    travel_started: int = 0
    moved: int = 0
    trained: int = 0

    @property
    def total_changes(self) -> int:
        return (
            self.travel_started
            + self.moved
            + self.trained
        )

@dataclass(frozen=True)
class NPCSimulationResult:
    changes: int = 0

@dataclass(frozen=True)
class WorldDevelopmentSimulationResult:
    changes: int = 0

@dataclass(frozen=True)
class KnowledgeSimulationResult:
    opportunities: int = 0
    resolvable_opportunities: int = 0
    propagations: int = 0
    opportunity_world_minutes: tuple[int, ...] = ()

@dataclass(frozen=True)
class WorldTickResult:
    simulated_player_arrivals: int = 0
    simulated_player_travel_started: int = 0
    simulated_player_moves: int = 0
    simulated_player_training: int = 0
    npc_changes: int = 0
    world_development_changes: int = 0
    knowledge_social_opportunities: int = 0
    knowledge_propagations: int = 0

    @property
    def total_changes(self) -> int:
        return (
            self.simulated_player_arrivals
            + self.simulated_player_travel_started
            + self.simulated_player_moves
            + self.simulated_player_training
            + self.npc_changes
            + self.world_development_changes
            + self.knowledge_propagations
        )

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0
