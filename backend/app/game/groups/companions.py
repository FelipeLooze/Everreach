"""Playable groups: the character inviting someone to travel together.

Group/invite primitives (Phase 13A/13B) existed, but nothing in play called
them. An invitation is still a real GroupInvite answered by the invited
person: a transported person accepts when they already know the character
and aren't committed to another group; villagers decline because nothing
models them leaving their duties yet. Companions then follow the character
when they travel, and autonomous simulation leaves them alone.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, EventType, GroupType
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.db.models.group import Group, GroupMember
from app.db.models.location import Location
from app.db.models.simulated_player import SimulatedPlayer
from app.game.groups.service import (
    accept_invite,
    active_group_for_member,
    active_group_members,
    create_group,
    decline_invite,
    disband_group,
    invite_to_group,
    remove_member,
)
from app.game.players.groups import active_group_for_player


@dataclass(frozen=True)
class GroupChange:
    summary: str
    changed: bool


def _has_met(db: Session, campaign_id: str, character: Character, player: SimulatedPlayer) -> bool:
    return (
        db.query(WorldEvent.id)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.actor_type == "character",
            WorldEvent.actor_id == character.id,
            WorldEvent.event_type.in_(
                (
                    EventType.PLAYER_MET_SIMULATED_PLAYER.value,
                    EventType.PLAYER_TALKED_TO_SIMULATED_PLAYER.value,
                )
            ),
            WorldEvent.payload_json.contains(player.id),
        )
        .first()
        is not None
    )


def character_group(db: Session, character: Character) -> Group | None:
    return active_group_for_member(db, CombatActorType.CHARACTER, character.id)


def _own_group(db: Session, campaign_id: str, character: Character) -> Group:
    group = character_group(db, character)
    if group is not None:
        return group
    return create_group(
        db,
        campaign_id,
        group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
        purpose=f"Viajar com {character.name}.",
        location_id=character.location_id,
        leader_type=CombatActorType.CHARACTER,
        leader_id=character.id,
    )


def invite_simulated_player(
    db: Session, campaign_id: str, character: Character, player: SimulatedPlayer
) -> GroupChange:
    current = character_group(db, character)
    if current is not None and any(
        member.member_type == CombatActorType.SIMULATED_PLAYER and member.member_id == player.id
        for member in active_group_members(db, current.id)
    ):
        return GroupChange(f"{player.name} já viaja com {character.name}.", False)

    reason = None
    if active_group_for_member(db, CombatActorType.SIMULATED_PLAYER, player.id) is not None:
        reason = "já está em outro grupo"
    elif active_group_for_player(db, player.id) is not None:
        reason = "já viaja com o próprio grupo de transportados"
    elif not _has_met(db, campaign_id, character, player):
        reason = f"ainda não conhece {character.name} o bastante para viajar junto"

    group = _own_group(db, campaign_id, character)
    invite = invite_to_group(
        db,
        group,
        inviter_type=CombatActorType.CHARACTER,
        inviter_id=character.id,
        invited_type=CombatActorType.SIMULATED_PLAYER,
        invited_id=player.id,
    )
    if reason is not None:
        decline_invite(db, invite)
        if len(active_group_members(db, group.id)) <= 1:
            disband_group(db, group)
        return GroupChange(f"{player.name} recusa o convite: {reason}.", False)

    accept_invite(db, invite)
    return GroupChange(f"{player.name} aceita viajar com {character.name}.", True)


def decline_for_duties(character: Character, npc_name: str, location: Location | None) -> GroupChange:
    place = f" em {location.name}" if location is not None else ""
    return GroupChange(
        f"{npc_name} tem obrigações{place} e não pode acompanhar {character.name}.", False
    )


def leave_character_group(db: Session, character: Character) -> GroupChange:
    group = character_group(db, character)
    if group is None:
        return GroupChange(f"{character.name} não está em nenhum grupo.", False)
    if group.leader_type == CombatActorType.CHARACTER and group.leader_id == character.id:
        disband_group(db, group)
        return GroupChange(f"{character.name} desfaz o grupo; cada um segue seu caminho.", True)
    remove_member(db, group, CombatActorType.CHARACTER, character.id)
    return GroupChange(f"{character.name} deixa o grupo.", True)


def companions_of(db: Session, character: Character) -> list[SimulatedPlayer]:
    group = character_group(db, character)
    if group is None:
        return []
    return [
        player
        for member in active_group_members(db, group.id)
        if member.member_type == CombatActorType.SIMULATED_PLAYER
        and (player := db.get(SimulatedPlayer, member.member_id)) is not None
    ]


def follow_character(db: Session, character: Character, origin_location_id: str) -> list[SimulatedPlayer]:
    """Companions standing where the character left from arrive with them."""
    moved = []
    for player in companions_of(db, character):
        if player.location_id != origin_location_id:
            continue
        player.location_id = character.location_id
        player.travel_connection_id = None
        player.travel_destination_id = None
        player.travel_started_world_minute = None
        player.travel_arrival_world_minute = None
        moved.append(player)
    group = character_group(db, character)
    if group is not None:
        group.location_id = character.location_id
    if moved or group is not None:
        db.flush()
    return moved


def accompanies_a_character(db: Session, player: SimulatedPlayer) -> bool:
    group = active_group_for_member(db, CombatActorType.SIMULATED_PLAYER, player.id)
    if group is None:
        return False
    return any(
        member.member_type == CombatActorType.CHARACTER
        for member in active_group_members(db, group.id)
    )
