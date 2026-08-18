import hashlib
from sqlalchemy.orm import Session
from app.game.time.clock import get_world_time
from app.simulation.results import KnowledgeSimulationResult
from dataclasses import dataclass
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.event import WorldEvent
from app.services.event_log import log_event
from app.game.npcs.service import (
    propagate_fact_locally,
)
from app.db.models.knowledge import (
    KnowledgeFact,
    KnowledgeKnower,
)
from app.simulation.cadence import (
    boundary_minutes_crossed,
)
from app.core.enums import (
    EventType,
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

@dataclass(frozen=True)
class SocialPair:
    first: SocialParticipant
    second: SocialParticipant

@dataclass(frozen=True)
class SocialTransferCandidate:
    source: SocialParticipant
    target: SocialParticipant
    fact_key: str

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

    propagations = 0

    if opportunity_world_minutes:
        current_opportunity = (
            opportunity_world_minutes[-1]
        )

        if resolve_social_opportunity(
            db,
            campaign_id,
            current_opportunity,
        ):
            propagations += 1

    return KnowledgeSimulationResult(
        opportunities=len(
            opportunity_world_minutes
        ),
        resolvable_opportunities=(
            1
            if opportunity_world_minutes
            else 0
        ),
        propagations=propagations,
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

def eligible_social_pairs(
    db: Session,
    campaign_id: str,
) -> tuple[SocialPair, ...]:
    participants = eligible_social_participants(
        db,
        campaign_id,
    )

    pairs: list[SocialPair] = []

    for first_index, first in enumerate(
        participants
    ):
        for second in participants[
            first_index + 1:
        ]:
            if (
                first.location_id
                != second.location_id
            ):
                continue

            pairs.append(
                SocialPair(
                    first=first,
                    second=second,
                )
            )

    return tuple(pairs)

def select_social_pair(
    db: Session,
    campaign_id: str,
    opportunity_world_minute: int,
) -> SocialPair | None:
    pairs = eligible_social_pairs(
        db,
        campaign_id,
    )

    if not pairs:
        return None

    seed = (
        f"{campaign_id}:"
        f"{opportunity_world_minute}"
    ).encode("utf-8")

    digest = hashlib.sha256(
        seed
    ).digest()

    index = int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=False,
    ) % len(pairs)

    return pairs[index]

def _known_fact_ids(
    db: Session,
    participant: SocialParticipant,
) -> set[str]:
    rows = (
        db.query(KnowledgeKnower.fact_id)
        .filter(
            KnowledgeKnower.knower_type
            == participant.knower_type.value,
            KnowledgeKnower.knower_id
            == participant.knower_id,
        )
        .all()
    )

    return {
        fact_id
        for (fact_id,) in rows
    }


def eligible_transfer_candidates(
    db: Session,
    campaign_id: str,
    pair: SocialPair,
) -> tuple[SocialTransferCandidate, ...]:
    first_known = _known_fact_ids(
        db,
        pair.first,
    )

    second_known = _known_fact_ids(
        db,
        pair.second,
    )

    candidates: list[
        SocialTransferCandidate
    ] = []

    directions = (
        (
            pair.first,
            pair.second,
            first_known - second_known,
        ),
        (
            pair.second,
            pair.first,
            second_known - first_known,
        ),
    )

    for source, target, fact_ids in directions:
        if not fact_ids:
            continue

        facts = (
            db.query(KnowledgeFact)
            .filter(
                KnowledgeFact.campaign_id
                == campaign_id,
                KnowledgeFact.id.in_(
                    fact_ids
                ),
                KnowledgeFact.is_secret.is_(False),
            )
            .order_by(
                KnowledgeFact.fact_key
            )
            .all()
        )

        for fact in facts:
            candidates.append(
                SocialTransferCandidate(
                    source=source,
                    target=target,
                    fact_key=fact.fact_key,
                )
            )

    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.source.knower_type.value,
                candidate.source.knower_id,
                candidate.target.knower_type.value,
                candidate.target.knower_id,
                candidate.fact_key,
            ),
        )
    )

def select_transfer_candidate(
    db: Session,
    campaign_id: str,
    pair: SocialPair,
    opportunity_world_minute: int,
) -> SocialTransferCandidate | None:
    candidates = eligible_transfer_candidates(
        db,
        campaign_id,
        pair,
    )

    if not candidates:
        return None

    seed = (
        f"{campaign_id}:"
        f"{opportunity_world_minute}:"
        f"{pair.first.knower_type.value}:"
        f"{pair.first.knower_id}:"
        f"{pair.second.knower_type.value}:"
        f"{pair.second.knower_id}"
    ).encode("utf-8")

    digest = hashlib.sha256(
        seed
    ).digest()

    index = int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=False,
    ) % len(candidates)

    return candidates[index]

def _social_opportunity_actor_id(
    opportunity_world_minute: int,
) -> str:
    return (
        f"social:{opportunity_world_minute}"
    )


def social_opportunity_already_resolved(
    db: Session,
    campaign_id: str,
    opportunity_world_minute: int,
) -> bool:
    return (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign_id,
            WorldEvent.event_type
            == EventType
            .SOCIAL_KNOWLEDGE_OPPORTUNITY_RESOLVED
            .value,
            WorldEvent.actor_type
            == "knowledge_simulation",
            WorldEvent.actor_id
            == _social_opportunity_actor_id(
                opportunity_world_minute
            ),
        )
        .first()
        is not None
    )

def resolve_social_opportunity(
    db: Session,
    campaign_id: str,
    opportunity_world_minute: int,
) -> bool:
    if social_opportunity_already_resolved(
        db,
        campaign_id,
        opportunity_world_minute,
    ):
        return False

    pair = select_social_pair(
        db,
        campaign_id,
        opportunity_world_minute,
    )

    candidate = None
    propagated = False

    if pair is not None:
        candidate = select_transfer_candidate(
            db,
            campaign_id,
            pair,
            opportunity_world_minute,
        )

    if candidate is not None:
        propagated = propagate_fact_locally(
            db,
            campaign_id,
            candidate.fact_key,
            candidate.source.knower_type,
            candidate.source.knower_id,
            candidate.target.knower_type,
            candidate.target.knower_id,
        )

    log_event(
        db,
        campaign_id,
        EventType.SOCIAL_KNOWLEDGE_OPPORTUNITY_RESOLVED,
        actor_type="knowledge_simulation",
        actor_id=_social_opportunity_actor_id(
            opportunity_world_minute
        ),
        payload={
            "opportunity_world_minute": (
                opportunity_world_minute
            ),
            "source_type": (
                candidate.source.knower_type.value
                if candidate
                else None
            ),
            "source_id": (
                candidate.source.knower_id
                if candidate
                else None
            ),
            "target_type": (
                candidate.target.knower_type.value
                if candidate
                else None
            ),
            "target_id": (
                candidate.target.knower_id
                if candidate
                else None
            ),
            "fact_key": (
                candidate.fact_key
                if candidate
                else None
            ),
            "propagated": propagated,
        },
    )

    return propagated