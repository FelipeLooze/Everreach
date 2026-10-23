"""Playable membership: a character registering with (or leaving) an
organization in person.

Membership primitives (join_organization, roles) existed since Phase 13F,
but nothing in play ever called them — the character was permanently a
non-member. Registration is deliberately physical: it happens at the
organization's headquarters, with someone from its leadership present to
record it. Only guilds take open registration for now; other kinds of
organization have their own admission rules that no system models yet.
"""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    OrganizationMembershipStatus,
    OrganizationStatus,
    OrganizationType,
    TransportedPeopleStance,
)
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.organization import Organization, OrganizationMember, OrganizationRole
from app.game.npcs.service import effective_npc_location_id
from app.game.organizations.roles import create_role, join_organization, set_membership_status

ENTRY_ROLE_RANK = 100
_OPEN_REGISTRATION_TYPES = (OrganizationType.GUILD,)
_CLOSED_STANCES = (TransportedPeopleStance.FEARFUL,)


@dataclass(frozen=True)
class MembershipChange:
    summary: str
    changed: bool


def _normalize(text: str) -> str:
    import unicodedata

    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


def _mentioned(organization: Organization, raw_text: str) -> bool:
    """Does the text name this organization by its distinctive words
    ("aventureiros", "comerciantes"), ignoring generic ones?"""
    generic = {"guilda", "de", "da", "do", "dos", "das", "conselho", "ordem"}
    text = _normalize(raw_text)
    words = [word for word in _normalize(organization.name).split() if word not in generic and len(word) > 3]
    return any(word in text for word in words)


_MASCULINE_HEADS = {"conselho", "circulo", "clube", "bando", "cla", "templo", "sindicato"}


def _the(organization: Organization, preposition: str = "") -> str:
    """Portuguese article for an organization name: "a Guilda", "o Conselho";
    with preposition "em"/"de" → "na"/"no", "da"/"do"."""
    head = _normalize(organization.name).split()[0] if organization.name else ""
    masculine = head in _MASCULINE_HEADS
    article = {"": "o" if masculine else "a", "em": "no" if masculine else "na",
               "de": "do" if masculine else "da"}[preposition]
    return f"{article} {organization.name}"


def _capitalized(text: str) -> str:
    return text[:1].upper() + text[1:]


def _pick(organizations: list[Organization], raw_text: str) -> Organization | None:
    if not organizations:
        return None
    named = [organization for organization in organizations if _mentioned(organization, raw_text)]
    if len(named) == 1:
        return named[0]
    return organizations[0] if len(organizations) == 1 else None


def _leader_present(db: Session, organization: Organization, location_id: str) -> NPC | None:
    rows = (
        db.query(OrganizationMember, OrganizationRole)
        .join(OrganizationRole, OrganizationMember.role_id == OrganizationRole.id)
        .filter(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.member_type == CombatActorType.NPC,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .order_by(OrganizationRole.rank_order)
        .all()
    )
    for member, role in rows:
        if role.rank_order >= ENTRY_ROLE_RANK:
            continue
        npc = db.get(NPC, member.member_id)
        if npc is not None and npc.alive and effective_npc_location_id(npc) == location_id:
            return npc
    return None


def _entry_role(db: Session, organization: Organization) -> OrganizationRole:
    role = (
        db.query(OrganizationRole)
        .filter(
            OrganizationRole.organization_id == organization.id,
            OrganizationRole.rank_order == ENTRY_ROLE_RANK,
        )
        .first()
    )
    if role is not None:
        return role
    title = "Aventureiro Registrado" if "aventureiros" in _normalize(organization.name) else "Membro"
    return create_role(db, organization, title, rank_order=ENTRY_ROLE_RANK)


def _open_membership(db: Session, organization: Organization, character: Character):
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.member_type == CombatActorType.CHARACTER,
            OrganizationMember.member_id == character.id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .first()
    )


def register_with_organization(
    db: Session, campaign_id: str, character: Character, raw_text: str
) -> MembershipChange:
    # A transported guild has no counter to register at: its leader or a
    # founder standing here decides ("quero entrar na sua guilda").
    from app.game.organizations import player_guilds

    reachable = player_guilds.guilds_with_leadership_present(db, character.location_id)
    named_guilds = [pair for pair in reachable if _mentioned(pair[0], raw_text)]
    if len(named_guilds) == 1 or (
        len(reachable) == 1
        and re.search(r"\b(?:sua|vossa|tua)\s+(?:guilda|companhia|sociedade)\b|\bseu\s+bando\b",
                      _normalize(raw_text))
    ):
        organization, sponsor = named_guilds[0] if len(named_guilds) == 1 else reachable[0]
        change = player_guilds.request_membership(db, campaign_id, character, organization, sponsor)
        return MembershipChange(change.summary, change.changed)

    here = (
        db.query(Organization)
        .filter(
            Organization.campaign_id == campaign_id,
            Organization.headquarters_location_id == character.location_id,
            Organization.status == OrganizationStatus.ACTIVE,
        )
        .order_by(Organization.id)
        .all()
    )
    # An organization the player names takes precedence over whichever one
    # happens to be headquartered here ("quero entrar na guilda" said in the
    # square must not register them with the village council).
    named = [
        org
        for org in db.query(Organization)
        .filter(
            Organization.campaign_id == campaign_id,
            Organization.status == OrganizationStatus.ACTIVE,
            Organization.headquarters_location_id.isnot(None),
        )
        .all()
        if _mentioned(org, raw_text)
    ]
    if len(named) == 1 and named[0].headquarters_location_id != character.location_id:
        headquarters = db.get(Location, named[0].headquarters_location_id)
        return MembershipChange(
            f"O registro {_the(named[0], 'em')} é feito na sede"
            + (f", em {headquarters.name}." if headquarters else "."),
            False,
        )
    organization = named[0] if len(named) == 1 else _pick(here, raw_text)
    if organization is None:
        return MembershipChange(
            "Não há aqui nenhuma organização sediada onde se registrar.", False
        )

    existing = _open_membership(db, organization, character)
    if existing is not None:
        role = db.get(OrganizationRole, existing.role_id) if existing.role_id else None
        return MembershipChange(
            f"{character.name} já é membro {_the(organization, 'de')}"
            + (f" ({role.title})." if role else "."),
            False,
        )
    if organization.organization_type not in _OPEN_REGISTRATION_TYPES:
        return MembershipChange(
            f"{_capitalized(_the(organization))} não aceita registro aberto de novos membros.", False
        )
    if organization.transported_people_stance in _CLOSED_STANCES:
        return MembershipChange(
            f"{_capitalized(_the(organization))} não está aceitando Transportados.", False
        )
    registrar = _leader_present(db, organization, character.location_id)
    if registrar is None:
        return MembershipChange(
            f"Não há ninguém da liderança {_the(organization, 'de')} aqui para registrar "
            f"{character.name} agora.",
            False,
        )

    role = _entry_role(db, organization)
    join_organization(
        db, organization, CombatActorType.CHARACTER, character.id, role_id=role.id
    )
    return MembershipChange(
        f"{registrar.name} registra {character.name} {_the(organization, 'em')} como {role.title}.",
        True,
    )


def leave_organization(
    db: Session, campaign_id: str, character: Character, raw_text: str
) -> MembershipChange:
    memberships = (
        db.query(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .filter(
            Organization.campaign_id == campaign_id,
            OrganizationMember.member_type == CombatActorType.CHARACTER,
            OrganizationMember.member_id == character.id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .all()
    )
    if not memberships:
        return MembershipChange(f"{character.name} não é membro de nenhuma organização.", False)
    organizations = [organization for _member, organization in memberships]
    own = [org for org in organizations if org.origin == "TRANSPORTED_CREATED"]
    if len(own) == 1 and re.search(
        r"\b(?:minha|nossa)\s+guilda\b|\b(?:meu|nosso)\s+bando\b", _normalize(raw_text)
    ):
        organizations = own
    organization = _pick(organizations, raw_text)
    if organization is None:
        return MembershipChange(
            f"{character.name} é membro de mais de uma organização; diga de qual quer sair.",
            False,
        )
    member = next(member for member, org in memberships if org.id == organization.id)
    set_membership_status(db, member, OrganizationMembershipStatus.LEFT)
    from app.game.organizations.player_guilds import handle_departure

    aftermath = handle_departure(db, organization, member)
    return MembershipChange(f"{character.name} deixa {_the(organization)}.{aftermath}", True)
