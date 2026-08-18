"""NPC autonomous behavior (working, traveling, aging, dying, etc. — spec section 20).

NOT IMPLEMENTED in the MVP. NPCs are static: they stay at their seeded location and
do not act on their own yet. This module exists so `world_simulation.tick` has a
single, documented place to call into once NPC simulation is built, instead of
silently pretending NPCs are alive and active in the world.
"""

from sqlalchemy.orm import Session
from app.simulation.results import NPCSimulationResult

def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> NPCSimulationResult:
    return NPCSimulationResult()
