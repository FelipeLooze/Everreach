"""Phase 17O — Organization & NPC Geographic Knowledge."""

from app.core.enums import CombatActorType, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.organization import Organization
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, knows_geographic_aspect
from app.game.knowledge.organizations import (
    consult_organization_geographic_knowledge,
    grant_organization_geographic_knowledge,
    is_active_member,
)
from app.game.organizations.roles import active_members
from app.game.world.seed import create_campaign, seed_initial_region


def _real_organization_with_founder(db_session, campaign_id):
    organization = db_session.query(Organization).filter(Organization.campaign_id == campaign_id).first()
    founder_member = active_members(db_session, organization.id)[0]
    return organization, founder_member


def test_granting_organization_knowledge_makes_the_org_a_real_knower(db_session):
    campaign = create_campaign(db_session, "Conhecimento Da Guilda", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)
    organization, _founder = _real_organization_with_founder(db_session, campaign.id)

    ensure_geographic_fact(
        db_session, campaign.id, "subregion", "sub_trade_route_test", GeographicKnowledgeAspect.EXISTENCE,
        "Uma rota comercial atravessa essa área.",
    )
    grant_organization_geographic_knowledge(
        db_session, campaign.id, organization.id, "subregion", "sub_trade_route_test",
        GeographicKnowledgeAspect.EXISTENCE, source="registro da guilda",
    )

    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.ORGANIZATION, organization.id,
        "subregion", "sub_trade_route_test", GeographicKnowledgeAspect.EXISTENCE,
    ) is True


def test_only_an_actual_active_member_can_consult_organization_knowledge(db_session):
    campaign = create_campaign(db_session, "Consulta Restrita", world_seed=2)
    region, _village = seed_initial_region(db_session, campaign.id)
    organization, founder_member = _real_organization_with_founder(db_session, campaign.id)

    ensure_geographic_fact(
        db_session, campaign.id, "subregion", "sub_guild_secret_test", GeographicKnowledgeAspect.EXISTENCE,
        "Uma área registrada nos arquivos da guilda.",
    )
    grant_organization_geographic_knowledge(
        db_session, campaign.id, organization.id, "subregion", "sub_guild_secret_test",
        GeographicKnowledgeAspect.EXISTENCE, source="registro da guilda",
    )

    assert is_active_member(
        db_session, organization.id, CombatActorType(founder_member.member_type), founder_member.member_id
    ) is True

    consulted = consult_organization_geographic_knowledge(
        db_session, campaign.id, organization.id,
        CombatActorType(founder_member.member_type), founder_member.member_id,
        "subregion", "sub_guild_secret_test", GeographicKnowledgeAspect.EXISTENCE,
    )
    assert consulted is True
    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.NPC, founder_member.member_id,
        "subregion", "sub_guild_secret_test", GeographicKnowledgeAspect.EXISTENCE,
    ) is True


def test_a_non_member_gets_nothing(db_session):
    campaign = create_campaign(db_session, "Nao Membro Sem Acesso", world_seed=3)
    region, _village = seed_initial_region(db_session, campaign.id)
    organization, _founder = _real_organization_with_founder(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region_id=region.id)

    ensure_geographic_fact(
        db_session, campaign.id, "subregion", "sub_members_only_test", GeographicKnowledgeAspect.EXISTENCE,
        "Uma área registrada nos arquivos da guilda.",
    )
    grant_organization_geographic_knowledge(
        db_session, campaign.id, organization.id, "subregion", "sub_members_only_test",
        GeographicKnowledgeAspect.EXISTENCE, source="registro da guilda",
    )

    assert is_active_member(db_session, organization.id, CombatActorType.CHARACTER, logan.id) is False

    consulted = consult_organization_geographic_knowledge(
        db_session, campaign.id, organization.id,
        CombatActorType.CHARACTER, logan.id,
        "subregion", "sub_members_only_test", GeographicKnowledgeAspect.EXISTENCE,
    )
    assert consulted is False
    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "subregion", "sub_members_only_test", GeographicKnowledgeAspect.EXISTENCE,
    ) is False


def test_consulting_organization_records_preserves_precision_by_default(db_session):
    campaign = create_campaign(db_session, "Registro Preserva Precisao", world_seed=4)
    region, _village = seed_initial_region(db_session, campaign.id)
    organization, founder_member = _real_organization_with_founder(db_session, campaign.id)

    ensure_geographic_fact(
        db_session, campaign.id, "subregion", "sub_precise_record_test", GeographicKnowledgeAspect.DISTANCE,
        "Levantamento oficial: distância medida com precisão.",
    )
    grant_organization_geographic_knowledge(
        db_session, campaign.id, organization.id, "subregion", "sub_precise_record_test",
        GeographicKnowledgeAspect.DISTANCE, source="levantamento oficial",
        precision=GeographicPrecision.PRECISE,
    )

    consult_organization_geographic_knowledge(
        db_session, campaign.id, organization.id,
        CombatActorType(founder_member.member_type), founder_member.member_id,
        "subregion", "sub_precise_record_test", GeographicKnowledgeAspect.DISTANCE,
    )

    from app.game.knowledge.geography import geographic_knowledge_precision

    member_precision = geographic_knowledge_precision(
        db_session, campaign.id, KnowerType.NPC, founder_member.member_id,
        "subregion", "sub_precise_record_test", GeographicKnowledgeAspect.DISTANCE,
    )
    assert member_precision == GeographicPrecision.PRECISE
