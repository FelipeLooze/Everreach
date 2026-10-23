"""Transported society over months: arrivals become people, travel groups
become guilds.

Arrivals otherwise stay an abstract head count forever, so the world never
had more than the three seeded transported people to form a society. Here,
at most one person a week steps out of the abstract population (largest
pool first) as a persistent individual, bounded by PERSISTENT_TRANSPORTED_CAP
and generated deterministically — no model call in the background. A single
tick shorter than a week never materializes anyone, so arrivals still land
as abstract population first.

Guilds emerge slowly by design: none before GUILD_EMERGENCE_MIN_DAYS of
world time; then, once a week, a travel group that has stayed together for
GROUP_MIN_AGE_DAYS may found one, guilds recruit acquaintances standing
with a member, and seasoned informal guilds register with the settlement
council. Bandit crews never register.
"""

import random
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    EventType,
    GuildFocus,
    OrganizationFormality,
    OrganizationOrigin,
    OrganizationStatus,
    OrganizationType,
    OrganizationVisibility,
    RiskTolerance,
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
    SimulatedPlayerStatus,
)
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.organization import Organization
from app.db.models.relationship import SimulatedPlayerRelationship
from app.db.models.simulated_player import SimulatedPlayer, SimulatedPlayerPopulation
from app.db.models.simulated_player_group import SimulatedPlayerGroup
from app.game.organizations import player_guilds
from app.game.organizations.roles import join_organization
from app.game.organizations.service import create_organization
from app.game.players.groups import active_group_members
from app.game.time.clock import get_world_time
from app.game.world.generator import generate_npc_name
from app.services.event_log import log_event
from app.simulation.cadence import boundary_minutes_crossed

DAY = 24 * 60
PERSISTENT_TRANSPORTED_CAP = 36
MATERIALIZE_INTERVAL_MINUTES = 7 * DAY
GUILD_INTERVAL_MINUTES = 7 * DAY
GUILD_EMERGENCE_MIN_DAYS = 60
GROUP_MIN_AGE_DAYS = 14
FOUND_CHANCE = 0.25
BANDIT_CHANCE = 0.3
FORMALIZE_MIN_AGE_DAYS = 30
FORMALIZE_CHANCE = 0.35

GUILD_NAMES = {
    GuildFocus.ADVENTURERS: (
        "Companhia da Aurora", "Andarilhos do Limiar", "Irmandade da Estrada Velha",
        "Vanguarda de Ferro", "Ordem da Chama Errante", "Lanternas do Vale",
    ),
    GuildFocus.HUNTERS: (
        "Lobos Cinzentos", "Arcos do Norte", "Rastreadores da Mata",
        "Falcões do Ermo", "Presas de Prata", "Caçadores do Véu",
    ),
    GuildFocus.BANDITS: (
        "Corvos da Estrada", "Mãos Sujas", "Lâminas Noturnas",
        "Bando do Ermo", "Ratos de Beira-Rio", "Os Sem-Bandeira",
    ),
    GuildFocus.MERCHANTS: (
        "Liga dos Mercadores Errantes", "Companhia da Balança", "Caravana Livre",
        "Casa de Comércio dos Transportados", "Rota do Sal",
    ),
    GuildFocus.RESEARCHERS: (
        "Sociedade dos Olhos Abertos", "Círculo dos Que Perguntam", "Biblioteca Errante",
        "Academia dos Transportados", "Ordem do Mapa Inacabado",
    ),
}
_GOALS = {
    SimulatedPlayerArchetype.EXPLORER: (
        SimulatedPlayerGoalType.EXPLORE_REGION, "Mapear a região onde caiu."
    ),
    SimulatedPlayerArchetype.TRAINER: (
        SimulatedPlayerGoalType.TRAIN_SELF, "Ficar forte o bastante para sobreviver aqui."
    ),
    SimulatedPlayerArchetype.SOCIAL: (
        SimulatedPlayerGoalType.GATHER_KNOWLEDGE, "Entender este mundo conversando com quem vive nele."
    ),
    SimulatedPlayerArchetype.ADVENTURER: (
        SimulatedPlayerGoalType.SEEK_DANGER, "Provar o próprio valor enfrentando o desconhecido."
    ),
}


@dataclass(frozen=True)
class SocietySimulationResult:
    materialized: int = 0
    guilds_founded: int = 0
    recruits: int = 0
    guilds_formalized: int = 0


def tick(
    db: Session, campaign_id: str, minutes: int, rng: random.Random | None = None
) -> SocietySimulationResult:
    if minutes <= 0:
        return SocietySimulationResult()
    rng = rng or random.Random()
    now = get_world_time(db, campaign_id).total_minutes()
    materialized = sum(
        _materialize_one(db, campaign_id, rng, world_minute)
        for world_minute in boundary_minutes_crossed(now, minutes, MATERIALIZE_INTERVAL_MINUTES)
    )
    founded = recruits = formalized = 0
    for world_minute in boundary_minutes_crossed(now, minutes, GUILD_INTERVAL_MINUTES):
        if world_minute < GUILD_EMERGENCE_MIN_DAYS * DAY:
            continue
        founded += _found_guilds(db, campaign_id, rng, world_minute)
        recruits += _recruit(db, campaign_id, rng)
        formalized += _formalize(db, campaign_id, rng, world_minute)
    db.flush()
    return SocietySimulationResult(materialized, founded, recruits, formalized)


# --- Arrivals become people -------------------------------------------------


def _materialize_one(db: Session, campaign_id: str, rng: random.Random, now: int) -> int:
    persistent = (
        db.query(SimulatedPlayer)
        .filter(SimulatedPlayer.campaign_id == campaign_id)
        .count()
    )
    if persistent >= PERSISTENT_TRANSPORTED_CAP:
        return 0
    pools = [
        population
        for population in db.query(SimulatedPlayerPopulation)
        .filter(SimulatedPlayerPopulation.abstract_count > 0)
        .order_by(SimulatedPlayerPopulation.abstract_count.desc(), SimulatedPlayerPopulation.id)
        if (location := db.get(Location, population.location_id)) is not None
        and _campaign_of(db, location) == campaign_id
    ]
    if not pools:
        return 0
    population = pools[0]
    used_names = {
        name for (name,) in db.query(SimulatedPlayer.name).filter(SimulatedPlayer.campaign_id == campaign_id)
    } | {name for (name,) in db.query(NPC.name).filter(NPC.campaign_id == campaign_id)}
    archetype = rng.choice(list(_GOALS))
    goal_type, goal = _GOALS[archetype]
    player = SimulatedPlayer(
        campaign_id=campaign_id,
        name=generate_npc_name(rng, used_names),
        level=0,
        location_id=population.location_id,
        archetype=archetype,
        goal=goal,
        goal_type=goal_type,
        goal_subject=f"location:{population.location_id}",
        risk_tolerance=rng.choice(list(RiskTolerance)).value,
    )
    db.add(player)
    population.abstract_count -= 1
    db.flush()
    log_event(
        db, campaign_id, EventType.SIMULATED_PLAYER_MATERIALIZED,
        actor_type="simulated_player", actor_id=player.id,
        payload={"location_id": population.location_id, "archetype": archetype},
        occurred_world_minute=now,
    )
    return 1


def _campaign_of(db: Session, location: Location) -> str | None:
    from app.db.models.region import Region

    region = db.get(Region, location.region_id) if location.region_id else None
    return region.campaign_id if region is not None else None


# --- Groups become guilds ---------------------------------------------------


def _focus_for(leader: SimulatedPlayer, members: list[SimulatedPlayer], rng: random.Random) -> GuildFocus:
    bold = [member for member in members if member.risk_tolerance == RiskTolerance.BOLD]
    if leader.risk_tolerance == RiskTolerance.BOLD and len(bold) * 2 >= len(members) and rng.random() < BANDIT_CHANCE:
        return GuildFocus.BANDITS
    choices = {
        SimulatedPlayerArchetype.EXPLORER: (GuildFocus.ADVENTURERS, GuildFocus.RESEARCHERS),
        SimulatedPlayerArchetype.TRAINER: (GuildFocus.HUNTERS,),
        SimulatedPlayerArchetype.SOCIAL: (GuildFocus.MERCHANTS, GuildFocus.ADVENTURERS),
        SimulatedPlayerArchetype.ADVENTURER: (GuildFocus.ADVENTURERS, GuildFocus.HUNTERS),
    }.get(leader.archetype, (GuildFocus.ADVENTURERS,))
    return rng.choice(choices)


def _unused_name(db: Session, campaign_id: str, focus: GuildFocus, rng: random.Random) -> str:
    taken = {
        name.casefold() for (name,) in db.query(Organization.name).filter(Organization.campaign_id == campaign_id)
    }
    options = [name for name in GUILD_NAMES[focus] if name.casefold() not in taken]
    if options:
        return rng.choice(options)
    base = rng.choice(GUILD_NAMES[focus])
    suffix = 2
    while f"{base} {suffix}".casefold() in taken:
        suffix += 1
    return f"{base} {suffix}"


def _found_guilds(db: Session, campaign_id: str, rng: random.Random, world_minute: int) -> int:
    founded = 0
    groups = (
        db.query(SimulatedPlayerGroup)
        .filter(
            SimulatedPlayerGroup.campaign_id == campaign_id,
            SimulatedPlayerGroup.status == "ACTIVE",
            SimulatedPlayerGroup.created_world_minute <= world_minute - GROUP_MIN_AGE_DAYS * DAY,
        )
        .order_by(SimulatedPlayerGroup.id)
        .all()
    )
    for group in groups:
        members = active_group_members(db, group.id)
        free = [
            member for member in members
            if player_guilds.transported_guild_of(db, CombatActorType.SIMULATED_PLAYER, member.id) is None
        ]
        leader = db.get(SimulatedPlayer, group.leader_id)
        if leader is None or leader not in free or len(free) < 2 or rng.random() >= FOUND_CHANCE:
            continue
        focus = _focus_for(leader, free, rng)
        founders = [
            member for member in free
            if member.id != leader.id
            and not (focus == GuildFocus.BANDITS and member.risk_tolerance == RiskTolerance.CAUTIOUS)
        ][: player_guilds.INFORMAL_MEMBER_CAP - 1]
        if not founders:
            continue
        organization = create_organization(
            db,
            campaign_id,
            _unused_name(db, campaign_id, focus, rng),
            organization_type=player_guilds.FOCUS_TYPES[focus],
            origin=OrganizationOrigin.TRANSPORTED_CREATED,
            description=player_guilds._FOCUS_DESCRIPTIONS[focus],
            visibility=(
                OrganizationVisibility.SECRET if focus == GuildFocus.BANDITS
                else OrganizationVisibility.PRIVATE
            ),
            founder_type=CombatActorType.SIMULATED_PLAYER,
            founder_id=leader.id,
        )
        player_guilds._staff_new_guild(
            db, campaign_id, organization, focus,
            leader=(CombatActorType.SIMULATED_PLAYER, leader.id),
            founders=[(CombatActorType.SIMULATED_PLAYER, member.id) for member in founders],
        )
        founded += 1
    return founded


def _recruit(db: Session, campaign_id: str, rng: random.Random) -> int:
    recruits = 0
    guilds = (
        db.query(Organization)
        .filter(
            Organization.campaign_id == campaign_id,
            Organization.origin == OrganizationOrigin.TRANSPORTED_CREATED,
            Organization.status == OrganizationStatus.ACTIVE,
        )
        .order_by(Organization.id)
        .all()
    )
    for guild in guilds:
        members = player_guilds._active_members(db, guild)
        if (
            guild.formality != OrganizationFormality.FORMALLY_RECOGNIZED
            and len(members) >= player_guilds.INFORMAL_MEMBER_CAP
        ):
            continue
        member_ids = {member.member_id for member in members if member.member_type == CombatActorType.SIMULATED_PLAYER}
        member_locations = {
            player.location_id for player_id in member_ids
            if (player := db.get(SimulatedPlayer, player_id)) is not None
        }
        candidates = []
        for relationship in db.query(SimulatedPlayerRelationship).filter(
            SimulatedPlayerRelationship.campaign_id == campaign_id,
            SimulatedPlayerRelationship.familiarity >= 1,
            SimulatedPlayerRelationship.affinity >= 0,
        ):
            pair = {relationship.first_player_id, relationship.second_player_id}
            outsiders = pair - member_ids
            # Exactly one side already belongs to this guild.
            if len(outsiders) != 1:
                continue
            other = db.get(SimulatedPlayer, outsiders.pop())
            if (
                other is None
                or other.status != SimulatedPlayerStatus.ACTIVE.value
                or other.location_id not in member_locations
                or player_guilds.transported_guild_of(db, CombatActorType.SIMULATED_PLAYER, other.id) is not None
                or (guild.focus == GuildFocus.BANDITS and other.risk_tolerance == RiskTolerance.CAUTIOUS)
            ):
                continue
            candidates.append(other)
        if not candidates:
            continue
        recruit = sorted(candidates, key=lambda player: player.id)[0]
        join_organization(
            db, guild, CombatActorType.SIMULATED_PLAYER, recruit.id,
            role_id=player_guilds._role(db, guild, player_guilds.MEMBER_RANK).id,
        )
        recruits += 1
    return recruits


def _formalize(db: Session, campaign_id: str, rng: random.Random, world_minute: int) -> int:
    """Seasoned informal guilds register with a council: their settlement's
    own, or the region's when the settlement has none (mining towns and
    trade posts usually don't). Leader level is deliberately not required:
    transported people far from the protagonist are simulated coarsely and
    barely level, which would freeze every remote guild as informal."""
    formalized = 0
    guilds = (
        db.query(Organization)
        .filter(
            Organization.campaign_id == campaign_id,
            Organization.origin == OrganizationOrigin.TRANSPORTED_CREATED,
            Organization.status == OrganizationStatus.ACTIVE,
            Organization.formality == OrganizationFormality.INFORMAL,
            Organization.focus != GuildFocus.BANDITS,
            Organization.founder_type == CombatActorType.SIMULATED_PLAYER,
        )
        .order_by(Organization.id)
        .all()
    )
    for guild in guilds:
        if guild.founded_world_minute is not None and guild.founded_world_minute > world_minute - FORMALIZE_MIN_AGE_DAYS * DAY:
            continue
        members = player_guilds._active_members(db, guild)
        if len(members) < player_guilds.FORMALIZE_MIN_MEMBERS or rng.random() >= FORMALIZE_CHANCE:
            continue
        leader_row = next(
            (member for member in members if player_guilds._rank_of(db, member) == player_guilds.LEADER_RANK),
            None,
        )
        if leader_row is None or leader_row.member_type != CombatActorType.SIMULATED_PLAYER:
            continue
        leader = db.get(SimulatedPlayer, leader_row.member_id)
        settlement = player_guilds._settlement_of(db, leader.location_id) if leader else None
        if settlement is None:
            continue
        councils = (
            db.query(Organization)
            .filter(
                Organization.campaign_id == campaign_id,
                Organization.origin == OrganizationOrigin.NATIVE,
                Organization.status == OrganizationStatus.ACTIVE,
                Organization.organization_type.in_((OrganizationType.COMMUNITY, OrganizationType.POLITICAL)),
                Organization.headquarters_location_id.isnot(None),
            )
            .order_by(Organization.id)
            .all()
        )
        local = [council for council in councils if council.headquarters_location_id == settlement.id]
        regional = [
            council for council in councils
            if (seat := db.get(Location, council.headquarters_location_id)) is not None
            and seat.region_id == settlement.region_id
        ]
        authority = (local or regional or [None])[0]
        if authority is None:
            continue
        player_guilds.publish_formal_guild(db, campaign_id, guild, authority, settlement.region_id)
        formalized += 1
    return formalized
