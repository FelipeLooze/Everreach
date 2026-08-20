from sqlalchemy.orm import Session

from app.ai.memory_manager import create_memory
from app.core.enums import (
    EventType,
    KnowledgeCertainty,
    KnowerType,
    MemoryOwnerType,
    SimulatedPlayerActivity,
    SimulatedPlayerStatus,
)
from app.db.models.character import Character
from app.db.models.knowledge import KnowledgeFact
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.simulated_player_routine import SimulatedPlayerRoutine
from app.game.npcs.service import teach_fact
from app.game.players.groups import leave_group
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


def kill_simulated_player(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    *,
    cause: str,
    occurred_world_minute: int | None = None,
) -> bool:
    """Apply a permanent, authoritative death and inform local witnesses."""
    if player.campaign_id != campaign_id:
        raise ValueError("Simulated player does not belong to campaign.")
    if player.status == SimulatedPlayerStatus.DEAD.value:
        return False
    if not cause.strip():
        raise ValueError("A simulated player death requires a mechanical cause.")

    world_minute = (
        occurred_world_minute
        if occurred_world_minute is not None
        else get_world_time(db, campaign_id).total_minutes()
    )
    location_id = player.location_id
    player.status = SimulatedPlayerStatus.DEAD.value
    player.activity = SimulatedPlayerActivity.AVAILABLE.value
    player.activity_until_world_minute = None
    player.travel_connection_id = None
    player.travel_destination_id = None
    player.travel_started_world_minute = None
    player.travel_arrival_world_minute = None
    db.query(SimulatedPlayerRoutine).filter(
        SimulatedPlayerRoutine.simulated_player_id == player.id,
        SimulatedPlayerRoutine.enabled.is_(True),
    ).update({SimulatedPlayerRoutine.enabled: False}, synchronize_session=False)
    leave_group(db, player.id, occurred_world_minute=world_minute)

    fact_key = f"simulated_player_death:{player.id}"
    fact = KnowledgeFact(
        campaign_id=campaign_id,
        subject=f"simulated_player:{player.id}",
        fact_key=fact_key,
        statement=f"{player.name} morreu. Causa registrada: {cause}.",
        social_priority=5,
    )
    db.add(fact)
    db.flush()
    event = log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_DIED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={
            "simulated_player_id": player.id,
            "name": player.name,
            "cause": cause,
            "location_id": location_id,
            "fact_id": fact.id,
            "fact_key": fact_key,
        },
        importance=5,
        occurred_world_minute=world_minute,
    )

    witnesses: list[tuple[KnowerType, MemoryOwnerType, str]] = []
    witnesses.extend(
        (KnowerType.NPC, MemoryOwnerType.NPC, npc_id)
        for (npc_id,) in db.query(NPC.id).filter(
            NPC.campaign_id == campaign_id,
            NPC.location_id == location_id,
            NPC.alive.is_(True),
            NPC.incapacitated.is_(False),
        )
    )
    witnesses.extend(
        (KnowerType.SIMULATED_PLAYER, MemoryOwnerType.SIMULATED_PLAYER, other_id)
        for (other_id,) in db.query(SimulatedPlayer.id).filter(
            SimulatedPlayer.campaign_id == campaign_id,
            SimulatedPlayer.location_id == location_id,
            SimulatedPlayer.status == SimulatedPlayerStatus.ACTIVE.value,
            SimulatedPlayer.id != player.id,
        )
    )
    witnesses.extend(
        (KnowerType.PLAYER, MemoryOwnerType.PLAYER, character_id)
        for (character_id,) in db.query(Character.id).filter(
            Character.campaign_id == campaign_id,
            Character.location_id == location_id,
            Character.status == "ALIVE",
        )
    )
    for knower_type, memory_type, witness_id in witnesses:
        teach_fact(
            db,
            campaign_id,
            fact_key,
            knower_type,
            witness_id,
            source="testemunho direto",
            certainty=KnowledgeCertainty.CONFIRMED,
        )
        create_memory(
            db,
            campaign_id,
            memory_type,
            witness_id,
            f"simulated_player:{player.id}",
            f"Testemunhou a morte de {player.name}. Causa: {cause}.",
            importance=5,
            source_event=event,
        )
    db.flush()
    return True
