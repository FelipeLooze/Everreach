"""Guilds founded by transported people, MMO-style, played from the
protagonist's side.

A guild is born from a travel group whose members agree (Phase 13E: no
"create guild" button, never a lone declaration). It starts INFORMAL —
private (secret, for bandits), known to its members, capped at
INFORMAL_MEMBER_CAP — and becomes FORMALLY_RECOGNIZED only by registering
it in person with a native authority: then it is public, the region's
natives know of it, and it may grow without the cap. Bandit crews can
never be registered.
"""

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    GuildFocus,
    KnowerType,
    KnowledgeCertainty,
    OrganizationFormality,
    OrganizationMembershipStatus,
    OrganizationOrigin,
    OrganizationReputationCategory,
    OrganizationStatus,
    OrganizationType,
    OrganizationVisibility,
    RiskTolerance,
)
from app.db.models.character import Character
from app.db.models.knowledge import KnowledgeFact
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.organization import Organization, OrganizationMember, OrganizationRole
from app.db.models.simulated_player import SimulatedPlayer
from app.game.groups.companions import _has_met, character_group, companions_of
from app.game.npcs.service import teach_fact
from app.game.organizations.registration import _leader_present
from app.game.organizations.reputation import (
    organization_reputation_category,
    organization_reputation_score,
)
from app.game.organizations.roles import change_member_role, create_role, join_organization, set_membership_status
from app.game.organizations.service import set_organization_status
from app.game.organizations.transported import (
    formally_recognize_organization,
    found_organization_from_group,
)

INFORMAL_MEMBER_CAP = 5
FORMALIZE_MIN_MEMBERS = 3
LEADER_RANK = 0
FOUNDER_RANK = 50
MEMBER_RANK = 100

FOCUS_TYPES = {
    GuildFocus.ADVENTURERS: OrganizationType.GUILD,
    GuildFocus.HUNTERS: OrganizationType.GUILD,
    GuildFocus.BANDITS: OrganizationType.CRIMINAL,
    GuildFocus.MERCHANTS: OrganizationType.COMMERCIAL,
    GuildFocus.RESEARCHERS: OrganizationType.ACADEMIC,
}
_FOCUS_DESCRIPTIONS = {
    GuildFocus.ADVENTURERS: "Guilda de aventureiros fundada por Transportados.",
    GuildFocus.HUNTERS: "Guilda de caçadores fundada por Transportados.",
    GuildFocus.BANDITS: "Bando fora da lei formado por Transportados.",
    GuildFocus.MERCHANTS: "Guilda de comerciantes fundada por Transportados.",
    GuildFocus.RESEARCHERS: "Sociedade de pesquisadores fundada por Transportados.",
}
# Checked in order: "bando de caçadores" is still a bandit crew.
_FOCUS_KEYWORDS = (
    (GuildFocus.BANDITS, r"\b(?:bando|bandid\w*|ladr\w*|criminos\w*|fora da lei)\b"),
    (GuildFocus.HUNTERS, r"\b(?:cacador\w*|caca)\b"),
    (GuildFocus.MERCHANTS, r"\b(?:comerci\w*|mercad\w*|negociant\w*)\b"),
    (GuildFocus.RESEARCHERS, r"\b(?:pesquis\w*|estudios\w*|erudit\w*|sabios?)\b"),
    (GuildFocus.ADVENTURERS, r"\baventur\w*\b"),
)
_QUOTED_NAME = re.compile(r'["“]([^"”]{2,60})["”]')
_CALLED_NAME = re.compile(r"\bchamad[oa]\s+(.+?)\s*(?:[.!?;,]|$)", re.IGNORECASE)


@dataclass(frozen=True)
class GuildChange:
    summary: str
    changed: bool


def _normalize(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


def parse_focus(raw_text: str) -> GuildFocus:
    text = _normalize(raw_text)
    for focus, pattern in _FOCUS_KEYWORDS:
        if re.search(pattern, text):
            return focus
    return GuildFocus.ADVENTURERS


def parse_guild_name(raw_text: str) -> str | None:
    match = _QUOTED_NAME.search(raw_text) or _CALLED_NAME.search(raw_text)
    if match is None:
        return None
    name = match.group(1).strip(" \t'\"“”")
    return name[:1].upper() + name[1:] if name else None


def _transported_membership(db: Session, member_type: CombatActorType, member_id: str):
    """The (member, organization) of an active transported-founded guild."""
    return (
        db.query(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .filter(
            OrganizationMember.member_type == member_type,
            OrganizationMember.member_id == member_id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
            Organization.origin == OrganizationOrigin.TRANSPORTED_CREATED,
            Organization.status == OrganizationStatus.ACTIVE,
        )
        .first()
    )


def _active_members(db: Session, organization: Organization) -> list[OrganizationMember]:
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .all()
    )


def _role(db: Session, organization: Organization, rank: int) -> OrganizationRole:
    role = (
        db.query(OrganizationRole)
        .filter(OrganizationRole.organization_id == organization.id, OrganizationRole.rank_order == rank)
        .first()
    )
    if role is not None:
        return role
    bandits = organization.focus == GuildFocus.BANDITS
    title = {
        LEADER_RANK: "Líder do Bando" if bandits else "Mestre da Guilda",
        FOUNDER_RANK: "Membro Fundador",
        MEMBER_RANK: "Membro",
    }[rank]
    return create_role(db, organization, title, rank_order=rank)


def _rank_of(db: Session, member: OrganizationMember) -> int:
    role = db.get(OrganizationRole, member.role_id) if member.role_id else None
    return role.rank_order if role is not None else MEMBER_RANK


def _refusal(organization_focus: GuildFocus, player: SimulatedPlayer) -> str | None:
    if organization_focus == GuildFocus.BANDITS and player.risk_tolerance == RiskTolerance.CAUTIOUS:
        return "não quer se envolver com um bando fora da lei"
    return None


def found_guild(
    db: Session,
    campaign_id: str,
    character: Character,
    raw_text: str,
    name_hint: str | None = None,
) -> GuildChange:
    existing = _transported_membership(db, CombatActorType.CHARACTER, character.id)
    if existing is not None:
        return GuildChange(
            f"{character.name} já faz parte de \"{existing[1].name}\"; saia dela antes de fundar outra.",
            False,
        )
    group = character_group(db, character)
    companions = [
        player for player in companions_of(db, character)
        if player.location_id == character.location_id
    ]
    if group is None or not companions:
        return GuildChange(
            "Fundar uma guilda exige ao menos mais um transportado viajando com "
            f"{character.name} e de acordo com a ideia.",
            False,
        )
    name = parse_guild_name(raw_text)
    generic_names = {"guilda", "bando", "sociedade", "companhia", "uma guilda", "a guilda"}
    if name is None and name_hint and _normalize(name_hint.strip()) not in generic_names:
        name = name_hint.strip()
    if name is None:
        return GuildChange(
            'Diga o nome da guilda (por exemplo: fundamos uma guilda chamada "Forja de Ferro").',
            False,
        )
    if any(
        _normalize(other.name) == _normalize(name)
        for other in db.query(Organization).filter(Organization.campaign_id == campaign_id)
    ):
        return GuildChange(f'Já existe uma organização chamada "{name}".', False)

    focus = parse_focus(raw_text)
    founders, refusals = [], []
    for player in companions:
        if _transported_membership(db, CombatActorType.SIMULATED_PLAYER, player.id) is not None:
            refusals.append(f"{player.name} já pertence a outra guilda")
        elif (reason := _refusal(focus, player)) is not None:
            refusals.append(f"{player.name} {reason}")
        else:
            founders.append(player)
    founders = founders[: INFORMAL_MEMBER_CAP - 1]
    if not founders:
        return GuildChange(
            "Ninguém do grupo aceita fundar a guilda: " + "; ".join(refusals) + ".", False
        )

    organization = found_organization_from_group(
        db,
        group,
        name,
        organization_type=FOCUS_TYPES[focus],
        description=_FOCUS_DESCRIPTIONS[focus],
        visibility=(
            OrganizationVisibility.SECRET if focus == GuildFocus.BANDITS
            else OrganizationVisibility.PRIVATE
        ),
        complete_group=False,
    )
    organization.focus = focus
    join_organization(
        db, organization, CombatActorType.CHARACTER, character.id,
        role_id=_role(db, organization, LEADER_RANK).id,
    )
    founder_role = _role(db, organization, FOUNDER_RANK)
    for player in founders:
        join_organization(
            db, organization, CombatActorType.SIMULATED_PLAYER, player.id, role_id=founder_role.id
        )
    db.flush()
    summary = (
        f'{character.name} funda "{name}" com {", ".join(player.name for player in founders)}. '
        "A guilda nasce informal: conhecida apenas por seus membros."
    )
    if refusals:
        summary += " Não entram: " + "; ".join(refusals) + "."
    return GuildChange(summary, True)


def _led_guild(db: Session, character: Character, *, max_rank: int):
    row = _transported_membership(db, CombatActorType.CHARACTER, character.id)
    if row is None:
        return None, None
    member, organization = row
    if _rank_of(db, member) > max_rank:
        return member, None
    return member, organization


def recruit(db: Session, campaign_id: str, character: Character, player: SimulatedPlayer) -> GuildChange:
    member, organization = _led_guild(db, character, max_rank=FOUNDER_RANK)
    if member is None:
        return GuildChange(f"{character.name} não pertence a nenhuma guilda de Transportados.", False)
    if organization is None:
        return GuildChange("Só o líder e os fundadores podem recrutar novos membros.", False)

    current = _transported_membership(db, CombatActorType.SIMULATED_PLAYER, player.id)
    if current is not None and current[1].id == organization.id:
        return GuildChange(f'{player.name} já é membro de "{organization.name}".', False)
    if current is not None:
        return GuildChange(f'{player.name} recusa: já pertence a "{current[1].name}".', False)
    if not _has_met(db, campaign_id, character, player):
        return GuildChange(f"{player.name} recusa: ainda não conhece {character.name}.", False)
    if (reason := _refusal(GuildFocus(organization.focus or GuildFocus.ADVENTURERS), player)) is not None:
        return GuildChange(f"{player.name} recusa: {reason}.", False)
    if (
        organization.formality != OrganizationFormality.FORMALLY_RECOGNIZED
        and len(_active_members(db, organization)) >= INFORMAL_MEMBER_CAP
    ):
        return GuildChange(
            f'"{organization.name}" já tem {INFORMAL_MEMBER_CAP} membros: uma guilda informal não '
            "cresce além disso. Registrá-la no Conselho permite crescer.",
            False,
        )
    join_organization(
        db, organization, CombatActorType.SIMULATED_PLAYER, player.id,
        role_id=_role(db, organization, MEMBER_RANK).id,
    )
    return GuildChange(f'{player.name} aceita entrar em "{organization.name}".', True)


def expel(db: Session, character: Character, player: SimulatedPlayer) -> GuildChange:
    member, organization = _led_guild(db, character, max_rank=LEADER_RANK)
    if member is None or organization is None:
        return GuildChange("Só o líder de uma guilda pode expulsar membros.", False)
    target = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.member_type == CombatActorType.SIMULATED_PLAYER,
            OrganizationMember.member_id == player.id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .first()
    )
    if target is None:
        return GuildChange(f'{player.name} não é membro de "{organization.name}".', False)
    set_membership_status(db, target, OrganizationMembershipStatus.EXPELLED)
    return GuildChange(f'{character.name} expulsa {player.name} de "{organization.name}".', True)


def _settlement_of(db: Session, location_id: str | None) -> Location | None:
    location = db.get(Location, location_id) if location_id else None
    while location is not None and location.parent_location_id:
        location = db.get(Location, location.parent_location_id)
    return location


def formalize(db: Session, campaign_id: str, character: Character) -> GuildChange:
    member, organization = _led_guild(db, character, max_rank=LEADER_RANK)
    if member is None or organization is None:
        return GuildChange("Só o líder de uma guilda de Transportados pode registrá-la.", False)
    if organization.formality == OrganizationFormality.FORMALLY_RECOGNIZED:
        return GuildChange(f'"{organization.name}" já é uma guilda registrada.', False)
    if organization.focus == GuildFocus.BANDITS:
        return GuildChange("Um bando fora da lei não pode ser registrado por nenhuma autoridade.", False)

    settlement = _settlement_of(db, character.location_id)
    authority = (
        db.query(Organization)
        .filter(
            Organization.campaign_id == campaign_id,
            Organization.origin == OrganizationOrigin.NATIVE,
            Organization.status == OrganizationStatus.ACTIVE,
            Organization.organization_type.in_((OrganizationType.COMMUNITY, OrganizationType.POLITICAL)),
            Organization.headquarters_location_id == character.location_id,
        )
        .first()
    )
    if authority is None:
        return GuildChange(
            "O registro de uma guilda é feito diante do conselho do povoado, na sede dele.", False
        )
    registrar = _leader_present(db, authority, character.location_id)
    if registrar is None:
        return GuildChange(f"Não há ninguém da liderança do {authority.name} aqui agora.", False)

    member_count = len(_active_members(db, organization))
    if member_count < FORMALIZE_MIN_MEMBERS:
        return GuildChange(
            f"{registrar.name} só registra guildas com ao menos {FORMALIZE_MIN_MEMBERS} membros; "
            f'"{organization.name}" tem {member_count}.',
            False,
        )
    vouching = [
        native
        for native in db.query(Organization).filter(
            Organization.campaign_id == campaign_id,
            Organization.origin == OrganizationOrigin.NATIVE,
            Organization.headquarters_location_id.isnot(None),
        )
        if _settlement_of(db, native.headquarters_location_id) == settlement
        and organization_reputation_category(
            organization_reputation_score(db, native.id, CombatActorType.CHARACTER, character.id)
        ) in (OrganizationReputationCategory.RELIABLE, OrganizationReputationCategory.TRUSTED)
    ]
    if not vouching:
        return GuildChange(
            f"{registrar.name} não registra a guilda: {character.name} ainda não tem reputação "
            "confiável com nenhuma instituição deste povoado.",
            False,
        )

    formally_recognize_organization(db, organization)
    organization.visibility = OrganizationVisibility.PUBLIC
    fact = KnowledgeFact(
        campaign_id=campaign_id,
        subject=f"organization:{organization.id}",
        fact_key=f"organization:{organization.id}:exists",
        statement=(
            f'Existe a guilda "{organization.name}", fundada por Transportados e registrada '
            f"no {authority.name}."
        ),
    )
    db.add(fact)
    db.flush()
    for native in db.query(NPC).filter(
        NPC.campaign_id == campaign_id, NPC.region_id == character.region_id, NPC.alive.is_(True)
    ):
        teach_fact(
            db, campaign_id, fact.fact_key, KnowerType.NPC, native.id,
            source="registro_de_guilda", certainty=KnowledgeCertainty.CONFIRMED,
        )
    return GuildChange(
        f'{registrar.name} registra "{organization.name}" no {authority.name}. A guilda passa a '
        "ser pública e pode crescer além de cinco membros.",
        True,
    )


def handle_departure(db: Session, organization: Organization, departed: OrganizationMember) -> str:
    """After a member leaves a transported guild: a departing leader hands
    the guild to the highest-ranked remaining member; an empty guild ends."""
    if organization.origin != OrganizationOrigin.TRANSPORTED_CREATED:
        return ""
    remaining = _active_members(db, organization)
    if not remaining:
        set_organization_status(db, organization, OrganizationStatus.DISBANDED)
        return f' "{organization.name}" deixa de existir.'
    if _rank_of(db, departed) != LEADER_RANK:
        return ""
    successor = min(remaining, key=lambda member: (_rank_of(db, member), member.joined_world_minute))
    change_member_role(db, successor, _role(db, organization, LEADER_RANK).id)
    name = db.get(SimulatedPlayer, successor.member_id)
    return f" A liderança passa para {name.name if name else 'outro membro'}."
