from sqlalchemy.orm import Session
from app.game.time.clock import get_world_time
from app.simulation.results import KnowledgeSimulationResult
from dataclasses import dataclass
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.simulation.cadence import (
    boundary_minutes_crossed,
)
from app.core.enums import (
    KnowerType,
    NPCActivity,
    SimulatedPlayerStatus,
)

SOCIAL_INTERVAL_MINUTES = 24 * 60

@dataclass(frozen=True)
class SocialParticipant:
    knower_type: KnowerType
    knower_id: str
    location_id: str

def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> KnowledgeSimulationResult:
    if minutes <= 0:
        return KnowledgeSimulationResult()

    current_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    opportunity_world_minutes = (
        boundary_minutes_crossed(
            current_world_minute,
            minutes,
            SOCIAL_INTERVAL_MINUTES,
        )
    )

    return KnowledgeSimulationResult(
        opportunities=len(
            opportunity_world_minutes
        ),
        resolvable_opportunities=(
            1
            if opportunity_world_minutes
            else 0
        ),
        opportunity_world_minutes=(
            opportunity_world_minutes
        ),
    )

def eligible_social_participants(
    db: Session,
    campaign_id: str,
) -> tuple[SocialParticipant, ...]:
    participants: list[SocialParticipant] = []

    npcs = (
        db.query(NPC)
        .filter(
            NPC.campaign_id == campaign_id,
            NPC.alive.is_(True),
            NPC.activity != NPCActivity.RESTING.value,
        )
        .order_by(NPC.id)
        .all()
    )

    for npc in npcs:
        participants.append(
            SocialParticipant(
                knower_type=KnowerType.NPC,
                knower_id=npc.id,
                location_id=npc.location_id,
            )
        )

    simulated_players = (
        db.query(SimulatedPlayer)
        .filter(
            SimulatedPlayer.campaign_id
            == campaign_id,
            SimulatedPlayer.status
            == SimulatedPlayerStatus.ACTIVE.value,
        )
        .order_by(SimulatedPlayer.id)
        .all()
    )

    for simulated_player in simulated_players:
        participants.append(
            SocialParticipant(
                knower_type=(
                    KnowerType.SIMULATED_PLAYER
                ),
                knower_id=simulated_player.id,
                location_id=(
                    simulated_player.location_id
                ),
            )
        )

    return tuple(
        sorted(
            participants,
            key=lambda participant: (
                participant.location_id,
                participant.knower_type.value,
                participant.knower_id,
            ),
        )
    )