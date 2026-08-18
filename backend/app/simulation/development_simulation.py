from sqlalchemy.orm import Session

from app.simulation.results import (
    WorldDevelopmentSimulationResult,
)


def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> WorldDevelopmentSimulationResult:
    """
    Advance persistent world developments.

    Mechanical development progression will be added
    incrementally. For now this establishes the World Tick
    subsystem contract without changing world state.
    """

    if minutes <= 0:
        return WorldDevelopmentSimulationResult()

    return WorldDevelopmentSimulationResult()