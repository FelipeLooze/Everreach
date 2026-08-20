from sqlalchemy.orm import Session

from app.core.enums import SimulatedPlayerStatus
from app.db.models.relationship import SimulatedPlayerRelationship
from app.db.models.simulated_player import SimulatedPlayer
from app.game.players.groups import active_group_for_player, create_group
from app.game.time.clock import get_world_time
from app.simulation.cadence import boundary_minutes_crossed
from app.simulation.results import SimulatedPlayerGroupSimulationResult


GROUP_INTERVAL_MINUTES = 24 * 60


def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> SimulatedPlayerGroupSimulationResult:
    if minutes <= 0:
        return SimulatedPlayerGroupSimulationResult()
    current = get_world_time(db, campaign_id).total_minutes()
    opportunities = boundary_minutes_crossed(
        current, minutes, GROUP_INTERVAL_MINUTES
    )
    formed = 0
    for world_minute in opportunities:
        relationships = (
            db.query(SimulatedPlayerRelationship)
            .filter(
                SimulatedPlayerRelationship.campaign_id == campaign_id,
                SimulatedPlayerRelationship.familiarity >= 1,
                SimulatedPlayerRelationship.affinity >= -20,
            )
            .order_by(
                SimulatedPlayerRelationship.trust.desc(),
                SimulatedPlayerRelationship.affinity.desc(),
                SimulatedPlayerRelationship.id,
            )
            .all()
        )
        for relationship in relationships:
            first = db.get(SimulatedPlayer, relationship.first_player_id)
            second = db.get(SimulatedPlayer, relationship.second_player_id)
            if (
                first is None
                or second is None
                or first.status != SimulatedPlayerStatus.ACTIVE.value
                or second.status != SimulatedPlayerStatus.ACTIVE.value
                or first.location_id != second.location_id
                or first.travel_arrival_world_minute is not None
                or second.travel_arrival_world_minute is not None
                or active_group_for_player(db, first.id) is not None
                or active_group_for_player(db, second.id) is not None
            ):
                continue
            create_group(
                db,
                campaign_id,
                first,
                [second],
                goal=first.goal or second.goal or "Sobreviver e explorar juntos.",
                occurred_world_minute=world_minute,
            )
            formed += 1
            break
    return SimulatedPlayerGroupSimulationResult(groups_formed=formed)
