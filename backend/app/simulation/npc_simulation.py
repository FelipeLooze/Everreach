from sqlalchemy.orm import Session

from app.db.models.npc import NPC
from app.game.time.clock import get_world_time
from app.simulation.npc_routines import activity_for_role
from app.simulation.results import NPCSimulationResult


def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> NPCSimulationResult:
    if minutes <= 0:
        return NPCSimulationResult()

    world_time = get_world_time(
        db,
        campaign_id,
    )

    npcs = (
        db.query(NPC)
        .filter(
            NPC.campaign_id == campaign_id,
            NPC.alive.is_(True),
        )
        .order_by(NPC.id)
        .all()
    )

    changes = 0

    for npc in npcs:
        expected_activity = activity_for_role(
            npc.role,
            world_time.hour,
        )

        if npc.activity == expected_activity:
            continue

        npc.activity = expected_activity
        changes += 1

    return NPCSimulationResult(
        changes=changes,
    )