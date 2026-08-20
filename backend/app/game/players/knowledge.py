from sqlalchemy.orm import Session

from app.core.enums import KnowerType
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game.npcs.service import propagate_fact_locally


def gather_local_knowledge(
    db: Session,
    player: SimulatedPlayer,
) -> bool:
    """Learn one shareable local fact the transported person does not know."""
    known_fact_ids = {
        fact_id
        for (fact_id,) in db.query(KnowledgeKnower.fact_id).filter(
            KnowledgeKnower.knower_type == KnowerType.SIMULATED_PLAYER.value,
            KnowledgeKnower.knower_id == player.id,
        )
    }
    local_sources: list[tuple[KnowerType, str]] = []
    local_sources.extend(
        (KnowerType.NPC, npc_id)
        for (npc_id,) in db.query(NPC.id).filter(
            NPC.campaign_id == player.campaign_id,
            NPC.location_id == player.location_id,
            NPC.alive.is_(True),
            NPC.incapacitated.is_(False),
        )
    )
    local_sources.extend(
        (KnowerType.SIMULATED_PLAYER, other_id)
        for (other_id,) in db.query(SimulatedPlayer.id).filter(
            SimulatedPlayer.campaign_id == player.campaign_id,
            SimulatedPlayer.location_id == player.location_id,
            SimulatedPlayer.id != player.id,
            SimulatedPlayer.status == "ACTIVE",
            SimulatedPlayer.travel_arrival_world_minute.is_(None),
        )
    )
    candidates = []
    for source_type, source_id in local_sources:
        query = (
            db.query(KnowledgeFact, KnowledgeKnower)
            .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
            .filter(
                KnowledgeFact.campaign_id == player.campaign_id,
                KnowledgeFact.is_secret.is_(False),
                KnowledgeFact.social_priority > 0,
                KnowledgeKnower.knower_type == source_type.value,
                KnowledgeKnower.knower_id == source_id,
            )
        )
        if known_fact_ids:
            query = query.filter(KnowledgeFact.id.notin_(known_fact_ids))
        for fact, _link in query.all():
            candidates.append((fact.social_priority, fact.fact_key, source_type, source_id))
    if not candidates:
        return False
    _, fact_key, source_type, source_id = sorted(
        candidates,
        key=lambda item: (-item[0], item[1], item[2].value, item[3]),
    )[0]
    return propagate_fact_locally(
        db,
        player.campaign_id,
        fact_key,
        source_type,
        source_id,
        KnowerType.SIMULATED_PLAYER,
        player.id,
    )
