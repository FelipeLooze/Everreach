"""Phase 13L — Conflicts & Politics.

A Conflict always carries a real, explained cause — never a bare
relation score. Not tied to exactly two organizations: INTERNAL_SCHISM
may name just one.
"""

import pytest

from app.core.enums import (
    OrganizationConflictStatus,
    OrganizationConflictType,
    OrganizationOrigin,
    OrganizationType,
)
from app.game.organizations.conflicts import (
    active_conflicts_for_organization,
    conflict_participants,
    create_conflict,
    set_conflict_status,
)
from app.game.organizations.service import OrganizationError, create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Conflicts")
    region, village = seed_initial_region(db_session, campaign.id)
    merchant_guild = create_organization(
        db_session, campaign.id, "Companhia Mercante",
        organization_type=OrganizationType.COMMERCIAL, origin=OrganizationOrigin.NATIVE,
    )
    mining_association = create_organization(
        db_session, campaign.id, "Associação de Mineração",
        organization_type=OrganizationType.COMMERCIAL, origin=OrganizationOrigin.NATIVE,
    )
    db_session.flush()
    return campaign, merchant_guild, mining_association


def test_conflict_requires_real_reasons_not_just_a_score(db_session):
    campaign, merchant_guild, mining_association = _setup(db_session)

    with pytest.raises(OrganizationError):
        create_conflict(
            db_session, campaign.id, "Controle da mina do leste",
            conflict_type=OrganizationConflictType.TERRITORIAL_DISPUTE,
            reasons="  ",
            participants=[(merchant_guild, None), (mining_association, None)],
        )


def test_conflict_persists_with_named_participants_and_reasons(db_session):
    campaign, merchant_guild, mining_association = _setup(db_session)

    conflict = create_conflict(
        db_session, campaign.id, "Controle da mina do leste",
        conflict_type=OrganizationConflictType.TERRITORIAL_DISPUTE,
        reasons="Disputa de propriedade; competição por recursos.",
        participants=[(merchant_guild, None), (mining_association, None)],
    )

    assert conflict.status == OrganizationConflictStatus.ACTIVE
    participants = conflict_participants(db_session, conflict.id)
    assert {p.id for p in participants} == {merchant_guild.id, mining_association.id}


def test_internal_schism_may_have_a_single_participant(db_session):
    campaign, merchant_guild, mining_association = _setup(db_session)

    conflict = create_conflict(
        db_session, campaign.id, "Cisão na Companhia Mercante",
        conflict_type=OrganizationConflictType.INTERNAL_SCHISM,
        reasons="Desacordo sobre sucessão da liderança.",
        participants=[(merchant_guild, None)],
    )

    assert conflict_participants(db_session, conflict.id) == [merchant_guild]


def test_resolving_a_conflict_removes_it_from_active_list(db_session):
    campaign, merchant_guild, mining_association = _setup(db_session)
    conflict = create_conflict(
        db_session, campaign.id, "Controle da mina do leste",
        conflict_type=OrganizationConflictType.TERRITORIAL_DISPUTE,
        reasons="Disputa de propriedade.",
        participants=[(merchant_guild, None), (mining_association, None)],
    )

    set_conflict_status(db_session, conflict, OrganizationConflictStatus.RESOLVED)

    assert conflict.resolved_world_minute is not None
    assert active_conflicts_for_organization(db_session, merchant_guild.id) == []


def test_a_conflict_requires_at_least_one_participant(db_session):
    campaign, merchant_guild, mining_association = _setup(db_session)

    with pytest.raises(OrganizationError):
        create_conflict(
            db_session, campaign.id, "Conflito sem ninguém",
            conflict_type=OrganizationConflictType.RIVALRY,
            reasons="Motivo qualquer.",
            participants=[],
        )


def test_conflict_can_carry_optional_sides(db_session):
    campaign, merchant_guild, mining_association = _setup(db_session)

    conflict = create_conflict(
        db_session, campaign.id, "Guerra comercial",
        conflict_type=OrganizationConflictType.WAR,
        reasons="Embargo mútuo declarado.",
        participants=[(merchant_guild, "aggressor"), (mining_association, "defender")],
    )

    from app.db.models.organization import OrganizationConflictParticipant

    rows = (
        db_session.query(OrganizationConflictParticipant)
        .filter(OrganizationConflictParticipant.conflict_id == conflict.id)
        .all()
    )
    sides = {row.organization_id: row.side for row in rows}
    assert sides[merchant_guild.id] == "aggressor"
    assert sides[mining_association.id] == "defender"
