"""Phase 17I — Expeditions.

An Expedition is a real world activity, not an artificial quest type
(spec) — built as a thin overlay on Group (Phase 13A already has
GroupType.EXPEDITION), reusing app.game.groups.service.create_group for
participants/leader/agency instead of a parallel membership system.

resolve_expedition is authoritative, same discipline as every other
Game Engine resolution: the Narrator describes what already happened,
it never decides the outcome. Deliberately NOT a giant survival
simulator (spec explicitly warns against this) — one d20 roll, modestly
helped by group size (more hands genuinely help, capped so a mob of 50
isn't mechanically required), against fixed thresholds separating
SUCCEEDED / PARTIAL_SUCCESS / FAILED. Richer dependencies (supplies,
equipment, season, route knowledge) are real, spec-listed possibilities
for a later, more detailed pass — not required for this foundation, and
not invented here as a placeholder.

NPC EXPEDITIONS (spec): nothing here requires a PLAYER leader or
participant — leader_type/founding_members accept CombatActorType.NPC
or SIMULATED_PLAYER just as easily. An expedition can be organized,
resolved, and grant its own members real geographic knowledge entirely
without the protagonist's involvement or awareness (spec's own
"DISCOVERY WITHOUT PLAYER" example) — see app.game.exploration.expeditions
having zero dependency on any specific Character in this module.
"""

import random

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    EventType,
    ExpeditionStatus,
    GeographicKnowledgeAspect,
    GroupType,
    KnowerType,
)
from app.db.models.expedition import Expedition
from app.game.dice import d20
from app.game.groups.service import active_group_members, create_group
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.time.clock import get_world_time
from app.services.event_log import log_event

_KNOWER_TYPE_BY_MEMBER_TYPE = {
    CombatActorType.CHARACTER.value: KnowerType.PLAYER,
    CombatActorType.NPC.value: KnowerType.NPC,
    CombatActorType.SIMULATED_PLAYER.value: KnowerType.SIMULATED_PLAYER,
}

_MEMBER_BONUS_CAP = 3
_SUCCESS_DC = 16
_PARTIAL_SUCCESS_DC = 10


def organize_expedition(
    db: Session,
    campaign_id: str,
    *,
    purpose: str,
    origin_location_id: str,
    founding_members: list[tuple[CombatActorType, str]],
    leader_type: CombatActorType | None = None,
    leader_id: str | None = None,
    target_subject_kind: str | None = None,
    target_entity_id: str | None = None,
    name: str | None = None,
) -> Expedition:
    group = create_group(
        db, campaign_id,
        group_type=GroupType.EXPEDITION,
        founding_members=founding_members,
        name=name,
        purpose=purpose,
        location_id=origin_location_id,
        leader_type=leader_type,
        leader_id=leader_id,
    )
    expedition = Expedition(
        campaign_id=campaign_id,
        group_id=group.id,
        purpose=purpose,
        target_subject_kind=target_subject_kind,
        target_entity_id=target_entity_id,
        origin_location_id=origin_location_id,
        status=ExpeditionStatus.PLANNED,
    )
    db.add(expedition)
    db.flush()
    return expedition


def begin_expedition(db: Session, campaign_id: str, expedition: Expedition) -> Expedition:
    if expedition.status != ExpeditionStatus.PLANNED.value:
        raise ValueError(f"Expedition {expedition.id} is not PLANNED (status={expedition.status}).")
    expedition.status = ExpeditionStatus.UNDERWAY.value
    expedition.started_world_minute = get_world_time(db, campaign_id).total_minutes()
    db.flush()
    log_event(
        db, campaign_id, EventType.EXPLORATION_ATTEMPTED,
        actor_type="expedition", actor_id=expedition.id,
        payload={"status": "underway", "purpose": expedition.purpose},
    )
    return expedition


def resolve_expedition(
    db: Session,
    campaign_id: str,
    expedition: Expedition,
    *,
    rng: random.Random | None = None,
) -> Expedition:
    if expedition.status != ExpeditionStatus.UNDERWAY.value:
        raise ValueError(f"Expedition {expedition.id} is not UNDERWAY (status={expedition.status}).")

    members = active_group_members(db, expedition.group_id)
    bonus = min(max(len(members) - 1, 0), _MEMBER_BONUS_CAP)
    roll = d20(modifier=bonus, rng=rng)

    if roll.total >= _SUCCESS_DC:
        outcome = ExpeditionStatus.SUCCEEDED
    elif roll.total >= _PARTIAL_SUCCESS_DC:
        outcome = ExpeditionStatus.PARTIAL_SUCCESS
    else:
        outcome = ExpeditionStatus.FAILED

    expedition.status = outcome.value
    expedition.resolved_world_minute = get_world_time(db, campaign_id).total_minutes()
    db.flush()

    if (
        outcome in (ExpeditionStatus.SUCCEEDED, ExpeditionStatus.PARTIAL_SUCCESS)
        and expedition.target_subject_kind
        and expedition.target_entity_id
    ):
        ensure_geographic_fact(
            db, campaign_id, expedition.target_subject_kind, expedition.target_entity_id,
            GeographicKnowledgeAspect.EXISTENCE,
            "Uma expedição confirmou a existência deste lugar.",
        )
        for member in members:
            knower_type = _KNOWER_TYPE_BY_MEMBER_TYPE.get(member.member_type)
            if knower_type is None:
                continue
            grant_geographic_knowledge(
                db, campaign_id, knower_type, member.member_id,
                expedition.target_subject_kind, expedition.target_entity_id,
                GeographicKnowledgeAspect.EXISTENCE,
                source="expedição",
            )

    log_event(
        db, campaign_id, EventType.EXPLORATION_ATTEMPTED,
        actor_type="expedition", actor_id=expedition.id,
        payload={"status": outcome.value, "roll": roll.total, "member_count": len(members)},
    )

    return expedition
