from sqlalchemy import false, not_, or_
from sqlalchemy.orm import Session

from app.db.models.npc import NPC
from app.game.time.clock import get_world_time
from app.simulation.npc_routines import activity_for_role
from app.simulation.results import NPCSimulationResult
from app.simulation.scope import SimulationScope, build_simulation_scope


def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
    scope: SimulationScope | None = None,
) -> NPCSimulationResult:
    if minutes <= 0:
        return NPCSimulationResult()

    world_time = get_world_time(
        db,
        campaign_id,
    )

    active_scope = scope or build_simulation_scope(db, campaign_id)

    individual_filter = false()
    if active_scope.detailed_location_ids:
        individual_filter = or_(
            individual_filter,
            NPC.location_id.in_(active_scope.detailed_location_ids),
        )
    if active_scope.relevant_npc_ids:
        individual_filter = or_(
            individual_filter,
            NPC.id.in_(active_scope.relevant_npc_ids),
        )

    base_filters = (
        NPC.campaign_id == campaign_id,
        NPC.alive.is_(True),
        NPC.incapacitated.is_(False),
    )

    if active_scope.unrestricted:
        npcs = (
            db.query(NPC)
            .filter(*base_filters)
            .order_by(NPC.id)
            .all()
        )
    else:
        npcs = (
            db.query(NPC)
            .filter(*base_filters, individual_filter)
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

    if not active_scope.unrestricted:
        # Distant, unknown NPCs only need their aggregate routine state. Update
        # them by role in SQL instead of materializing every row in Python.
        abstract_filter = not_(individual_filter)
        abstract_roles = (
            db.query(NPC.role)
            .filter(*base_filters, abstract_filter)
            .distinct()
            .all()
        )

        for (role,) in abstract_roles:
            expected_activity = activity_for_role(role, world_time.hour)
            updated = (
                db.query(NPC)
                .filter(
                    *base_filters,
                    abstract_filter,
                    NPC.role == role,
                    NPC.activity != expected_activity,
                )
                .update(
                    {NPC.activity: expected_activity},
                    synchronize_session=False,
                )
            )
            changes += updated

    return NPCSimulationResult(
        changes=changes,
    )
