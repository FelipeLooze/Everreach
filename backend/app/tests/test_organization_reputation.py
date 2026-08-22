"""Phase 13G — Reputation.

Never a bare score as the only source of truth — every change is an
explained, append-only record, and the category read back is derived
from the full history. Reputation is knowledge-dependent: an
organization does not magically know what happened unless one of its own
members actually knows the underlying fact.
"""

import pytest

from app.core.enums import (
    CombatActorType,
    KnowerType,
    OrganizationOrigin,
    OrganizationReputationCategory,
    OrganizationType,
)
from app.db.models.knowledge import KnowledgeFact
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.npcs.service import teach_fact
from app.game.organizations.reputation import (
    award_organization_reputation,
    organization_reputation_category,
    organization_reputation_history,
    organization_reputation_score,
)
from app.game.organizations.roles import join_organization
from app.game.organizations.service import OrganizationError, create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Reputation")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    db_session.flush()
    return campaign, region, village, character, osgar, org


def test_reputation_accumulates_from_explained_records(db_session):
    campaign, region, village, character, osgar, org = _setup(db_session)

    award_organization_reputation(
        db_session, org, CombatActorType.CHARACTER, character.id,
        delta=10, reason="Completou um contrato de escolta.",
    )
    award_organization_reputation(
        db_session, org, CombatActorType.CHARACTER, character.id,
        delta=5, reason="Devolveu equipamento emprestado.",
    )

    history = organization_reputation_history(db_session, org.id, CombatActorType.CHARACTER, character.id)
    assert [r.reason for r in history] == [
        "Completou um contrato de escolta.",
        "Devolveu equipamento emprestado.",
    ]
    score = organization_reputation_score(db_session, org.id, CombatActorType.CHARACTER, character.id)
    assert score == 15
    assert organization_reputation_category(score) == OrganizationReputationCategory.RELIABLE


def test_reputation_requires_an_explanation(db_session):
    campaign, region, village, character, osgar, org = _setup(db_session)

    with pytest.raises(OrganizationError):
        award_organization_reputation(
            db_session, org, CombatActorType.CHARACTER, character.id, delta=10, reason="  ",
        )


def test_two_organizations_hold_independent_reputations(db_session):
    campaign, region, village, character, osgar, org = _setup(db_session)
    other_org = create_organization(
        db_session, campaign.id, "Templo de Cardal",
        organization_type=OrganizationType.RELIGIOUS, origin=OrganizationOrigin.NATIVE,
    )

    award_organization_reputation(
        db_session, org, CombatActorType.CHARACTER, character.id, delta=15, reason="Confiável.",
    )
    award_organization_reputation(
        db_session, other_org, CombatActorType.CHARACTER, character.id, delta=-10, reason="Ofendeu um sacerdote.",
    )

    guild_score = organization_reputation_score(db_session, org.id, CombatActorType.CHARACTER, character.id)
    temple_score = organization_reputation_score(db_session, other_org.id, CombatActorType.CHARACTER, character.id)
    assert guild_score == 15
    assert temple_score == -10


def test_reputation_change_without_a_witness_is_refused(db_session):
    campaign, region, village, character, osgar, org = _setup(db_session)
    fact = KnowledgeFact(
        campaign_id=campaign.id, fact_key="logan_stole_supplies",
        statement="Logan roubou suprimentos da guilda.",
    )
    db_session.add(fact)
    db_session.commit()

    with pytest.raises(OrganizationError):
        award_organization_reputation(
            db_session, org, CombatActorType.CHARACTER, character.id,
            delta=-20, reason="Roubou suprimentos.", witness_fact_key="logan_stole_supplies",
        )


def test_reputation_change_with_a_witnessing_member_succeeds(db_session):
    campaign, region, village, character, osgar, org = _setup(db_session)
    fact = KnowledgeFact(
        campaign_id=campaign.id, fact_key="logan_stole_supplies",
        statement="Logan roubou suprimentos da guilda.",
    )
    db_session.add(fact)
    db_session.commit()
    join_organization(db_session, org, CombatActorType.NPC, osgar.id)
    teach_fact(db_session, campaign.id, "logan_stole_supplies", KnowerType.NPC, osgar.id)

    record = award_organization_reputation(
        db_session, org, CombatActorType.CHARACTER, character.id,
        delta=-20, reason="Roubou suprimentos.", witness_fact_key="logan_stole_supplies",
    )

    assert record.delta == -20


def test_category_thresholds(db_session):
    assert organization_reputation_category(25) == OrganizationReputationCategory.TRUSTED
    assert organization_reputation_category(10) == OrganizationReputationCategory.RELIABLE
    assert organization_reputation_category(0) == OrganizationReputationCategory.NEUTRAL
    assert organization_reputation_category(-10) == OrganizationReputationCategory.DISTRUSTED
    assert organization_reputation_category(-30) == OrganizationReputationCategory.HOSTILE


def test_no_history_reads_as_neutral(db_session):
    campaign, region, village, character, osgar, org = _setup(db_session)

    score = organization_reputation_score(db_session, org.id, CombatActorType.CHARACTER, character.id)

    assert score == 0
    assert organization_reputation_category(score) == OrganizationReputationCategory.NEUTRAL
