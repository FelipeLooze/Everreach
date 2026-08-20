from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.simulated_player import SimulatedPlayer, SimulatedPlayerSkill
from app.game.progression.service import xp_to_next_level
from app.services.event_log import log_event


def get_or_create_simulated_player_skill(
    db: Session,
    player: SimulatedPlayer,
    name: str,
) -> SimulatedPlayerSkill:
    skill = (
        db.query(SimulatedPlayerSkill)
        .filter(
            SimulatedPlayerSkill.simulated_player_id == player.id,
            SimulatedPlayerSkill.name == name,
        )
        .first()
    )
    if skill is None:
        skill = SimulatedPlayerSkill(
            simulated_player_id=player.id,
            name=name,
            mastery=0,
        )
        db.add(skill)
        db.flush()
    return skill


def award_simulated_player_xp(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    amount: float,
    *,
    occurred_world_minute: int | None = None,
) -> int:
    if amount <= 0:
        return 0
    if player.campaign_id != campaign_id:
        raise ValueError("Simulated player does not belong to campaign.")

    previous_level = player.level
    player.xp += amount
    while player.xp >= xp_to_next_level(player.level):
        player.xp -= xp_to_next_level(player.level)
        player.level += 1

    log_event(
        db,
        campaign_id,
        EventType.SIMULATED_PLAYER_GAINED_XP,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={
            "amount": amount,
            "current_xp": player.xp,
            "current_level": player.level,
        },
        occurred_world_minute=occurred_world_minute,
    )
    for new_level in range(previous_level + 1, player.level + 1):
        log_event(
            db,
            campaign_id,
            EventType.SIMULATED_PLAYER_LEVELED_UP,
            actor_type="simulated_player",
            actor_id=player.id,
            payload={"previous_level": new_level - 1, "new_level": new_level},
            occurred_world_minute=occurred_world_minute,
        )
    db.flush()
    return player.level - previous_level


def apply_training(
    db: Session,
    campaign_id: str,
    player: SimulatedPlayer,
    *,
    occurred_world_minute: int,
) -> int:
    """Apply one bounded training outcome and return levels gained."""
    skill = get_or_create_simulated_player_skill(db, player, "Sobrevivência")
    skill.mastery += 0.5
    return award_simulated_player_xp(
        db,
        campaign_id,
        player,
        2,
        occurred_world_minute=occurred_world_minute,
    )
