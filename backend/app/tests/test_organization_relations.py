"""Phase 13H — Organization Relationships.

Multiple relation types coexist between the same pair — proving
diplomacy is never collapsed into one exclusive value or a bare number.
Ending a relation preserves it in history rather than deleting it.
"""

from app.core.enums import OrganizationOrigin, OrganizationRelationType, OrganizationType
from app.game.organizations.relations import (
    active_relations_between,
    end_relation,
    establish_relation,
    relation_history_between,
)
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Relations")
    region, village = seed_initial_region(db_session, campaign.id)
    guild_a = create_organization(
        db_session, campaign.id, "Companhia Mercante do Norte",
        organization_type=OrganizationType.COMMERCIAL, origin=OrganizationOrigin.NATIVE,
    )
    guild_b = create_organization(
        db_session, campaign.id, "Companhia Mercante do Sul",
        organization_type=OrganizationType.COMMERCIAL, origin=OrganizationOrigin.NATIVE,
    )
    db_session.flush()
    return campaign, guild_a, guild_b


def test_two_relation_types_can_coexist_between_the_same_pair(db_session):
    campaign, guild_a, guild_b = _setup(db_session)

    establish_relation(
        db_session, guild_a, guild_b, OrganizationRelationType.TRADE_PARTNER,
        reason="Acordo de fornecimento de ferro.",
    )
    establish_relation(
        db_session, guild_a, guild_b, OrganizationRelationType.COMPETITOR,
        reason="Disputam os mesmos clientes na estrada do norte.",
    )

    relations = active_relations_between(db_session, guild_a.id, guild_b.id)
    assert {r.relation_type for r in relations} == {
        OrganizationRelationType.TRADE_PARTNER,
        OrganizationRelationType.COMPETITOR,
    }


def test_relation_is_symmetric_regardless_of_direction_queried(db_session):
    campaign, guild_a, guild_b = _setup(db_session)
    establish_relation(db_session, guild_a, guild_b, OrganizationRelationType.RIVAL)

    from_a = active_relations_between(db_session, guild_a.id, guild_b.id)
    from_b = active_relations_between(db_session, guild_b.id, guild_a.id)

    assert len(from_a) == 1 and len(from_b) == 1
    assert from_a[0].id == from_b[0].id


def test_establishing_the_same_relation_twice_returns_the_same_row(db_session):
    campaign, guild_a, guild_b = _setup(db_session)
    first = establish_relation(db_session, guild_a, guild_b, OrganizationRelationType.ALLIED)
    second = establish_relation(db_session, guild_a, guild_b, OrganizationRelationType.ALLIED)

    assert first.id == second.id


def test_ending_a_relation_preserves_it_in_history(db_session):
    campaign, guild_a, guild_b = _setup(db_session)
    relation = establish_relation(
        db_session, guild_a, guild_b, OrganizationRelationType.AT_WAR,
        reason="Disputa pela mina do leste.",
    )

    end_relation(db_session, relation, reason="Tratado de paz assinado.")

    assert relation.status == "ENDED"
    assert active_relations_between(db_session, guild_a.id, guild_b.id) == []
    history = relation_history_between(db_session, guild_a.id, guild_b.id)
    assert len(history) == 1
    assert history[0].reason == "Disputa pela mina do leste."


def test_a_new_relation_can_follow_an_ended_one(db_session):
    campaign, guild_a, guild_b = _setup(db_session)
    war = establish_relation(db_session, guild_a, guild_b, OrganizationRelationType.AT_WAR)
    end_relation(db_session, war, reason="Tratado assinado.")

    peace = establish_relation(
        db_session, guild_a, guild_b, OrganizationRelationType.TRADE_PARTNER,
        reason="Acordo comercial pós-guerra.",
    )

    history = relation_history_between(db_session, guild_a.id, guild_b.id)
    assert len(history) == 2
    assert active_relations_between(db_session, guild_a.id, guild_b.id) == [peace]


def test_organization_cannot_relate_to_itself(db_session):
    import pytest
    from app.game.organizations.service import OrganizationError

    campaign, guild_a, guild_b = _setup(db_session)

    with pytest.raises(OrganizationError):
        establish_relation(db_session, guild_a, guild_a, OrganizationRelationType.ALLIED)
