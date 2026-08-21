"""Phase 13M — Quest / Notice Integration.

Organizations become a real opportunity source without bypassing Phase
12's own quest/notice architecture — publish_organization_notice and
sponsor_quest are thin calls into post_notice/create_quest, not a
parallel system. Both leave a real OrganizationAction audit trail.
"""

import pytest

from app.core.enums import (
    NoticeCategory,
    OrganizationActionType,
    OrganizationNeedCategory,
    OrganizationOrigin,
    OrganizationType,
    QuestSource,
)
from app.db.models.location import LocationFeature
from app.game.organizations.actions import organization_action_history
from app.game.organizations.goals import create_need
from app.game.organizations.opportunities import publish_organization_notice, sponsor_quest
from app.game.organizations.service import OrganizationError, create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Opportunities")
    region, village = seed_initial_region(db_session, campaign.id)
    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    board = LocationFeature(location_id=village.id, name="Quadro de Avisos de Cardal")
    db_session.add(board)
    db_session.flush()
    return campaign, region, village, org, board


def test_published_notice_carries_organizational_authorship(db_session):
    campaign, region, village, org, board = _setup(db_session)
    need = create_need(
        db_session, org, "Mais caçadores disponíveis.",
        category=OrganizationNeedCategory.SKILLED_MEMBERS,
    )

    notice = publish_organization_notice(
        db_session, org, board.id,
        category=NoticeCategory.RECRUITMENT, title="Caçadores procurados",
        text="A guilda busca caçadores para patrulhar a estrada do norte.",
        need_id=need.id,
    )

    assert notice.author_organization_id == org.id
    assert notice.author_npc_id is None


def test_publishing_a_notice_leaves_an_organization_action_record(db_session):
    campaign, region, village, org, board = _setup(db_session)

    publish_organization_notice(
        db_session, org, board.id,
        category=NoticeCategory.WARNING, title="Estrada perigosa",
        text="Lobos avistados na estrada do norte.",
    )

    history = organization_action_history(db_session, org.id)
    assert len(history) == 1
    assert history[0].action_type == OrganizationActionType.PUBLISH_NOTICE


def test_notice_need_must_belong_to_the_publishing_organization(db_session):
    campaign, region, village, org, board = _setup(db_session)
    other_org = create_organization(
        db_session, campaign.id, "Templo de Cardal",
        organization_type=OrganizationType.RELIGIOUS, origin=OrganizationOrigin.NATIVE,
    )
    foreign_need = create_need(
        db_session, other_org, "Incenso.", category=OrganizationNeedCategory.MATERIALS,
    )

    with pytest.raises(OrganizationError):
        publish_organization_notice(
            db_session, org, board.id,
            category=NoticeCategory.TRADE, title="Compra de incenso",
            text="A guilda busca incenso.", need_id=foreign_need.id,
        )


def test_sponsored_quest_uses_the_reserved_organization_source(db_session):
    campaign, region, village, org, board = _setup(db_session)

    quest = sponsor_quest(
        db_session, org, region.id, "Escoltar caravana",
        "A guilda paga por uma escolta segura até Arven.",
        objectives=("Chegar a Arven em segurança.",),
    )

    assert quest.source == QuestSource.ORGANIZATION_REQUEST
    assert quest.sponsoring_organization_id == org.id


def test_sponsoring_a_quest_leaves_an_organization_action_record(db_session):
    campaign, region, village, org, board = _setup(db_session)

    sponsor_quest(db_session, org, region.id, "Escoltar caravana")

    history = organization_action_history(db_session, org.id)
    assert len(history) == 1
    assert "Escoltar caravana" in history[0].description
