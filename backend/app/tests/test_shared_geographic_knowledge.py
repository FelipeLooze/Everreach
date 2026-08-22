"""Phase 17M — Shared Geographic Knowledge."""

import pytest

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType, KnowledgeCertainty
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, geographic_knowledge_precision, grant_geographic_knowledge
from app.game.knowledge.sharing import propagate_geographic_knowledge
from app.game.world.seed import create_campaign


def test_verbal_sharing_degrades_precision_by_one_step(db_session):
    campaign = create_campaign(db_session, "Compartilhamento Verbal", world_seed=1)
    logan = create_character(db_session, campaign.id, "Logan")
    npc_id = "npc_guide_test"

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE,
        "Siga a estrada principal para o sul.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.NPC, npc_id, "settlement", "loc_arven",
        GeographicKnowledgeAspect.ROUTE, precision=GeographicPrecision.PRECISE,
    )

    propagated = propagate_geographic_knowledge(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE,
        KnowerType.NPC, npc_id, KnowerType.PLAYER, logan.id,
    )

    assert propagated is True
    logan_precision = geographic_knowledge_precision(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE
    )
    assert logan_precision == GeographicPrecision.GOOD


def test_a_map_style_transfer_preserves_precision(db_session):
    campaign = create_campaign(db_session, "Compartilhamento Por Mapa", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")
    npc_id = "npc_cartographer_test"

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE,
        "Siga a estrada principal para o sul.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.NPC, npc_id, "settlement", "loc_arven",
        GeographicKnowledgeAspect.ROUTE, precision=GeographicPrecision.PRECISE,
    )

    propagate_geographic_knowledge(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE,
        KnowerType.NPC, npc_id, KnowerType.PLAYER, logan.id,
        degrade_precision=False,
    )

    logan_precision = geographic_knowledge_precision(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE
    )
    assert logan_precision == GeographicPrecision.PRECISE


def test_vague_precision_has_no_further_floor(db_session):
    campaign = create_campaign(db_session, "Piso Vago", world_seed=3)
    logan = create_character(db_session, campaign.id, "Logan")
    npc_id = "npc_rumor_source_test"

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE, "Existe uma cidade.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.NPC, npc_id, "settlement", "loc_arven",
        GeographicKnowledgeAspect.EXISTENCE, precision=GeographicPrecision.VAGUE,
    )

    propagate_geographic_knowledge(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE,
        KnowerType.NPC, npc_id, KnowerType.PLAYER, logan.id,
    )

    logan_precision = geographic_knowledge_precision(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE
    )
    assert logan_precision == GeographicPrecision.VAGUE


def test_sharing_something_the_source_does_not_know_raises(db_session):
    campaign = create_campaign(db_session, "Fonte Nao Sabe", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE, "Existe uma cidade.",
    )

    with pytest.raises(ValueError):
        propagate_geographic_knowledge(
            db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE,
            KnowerType.NPC, "npc_who_never_learned", KnowerType.PLAYER, logan.id,
        )


def test_sharing_with_an_already_more_confident_target_is_a_no_op(db_session):
    campaign = create_campaign(db_session, "Alvo Ja Confiante", world_seed=5)
    logan = create_character(db_session, campaign.id, "Logan")
    npc_id = "npc_less_sure_test"

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE, "Existe uma cidade.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven",
        GeographicKnowledgeAspect.EXISTENCE, certainty=KnowledgeCertainty.CONFIRMED,
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.NPC, npc_id, "settlement", "loc_arven",
        GeographicKnowledgeAspect.EXISTENCE, certainty=KnowledgeCertainty.RUMOR,
    )

    propagated = propagate_geographic_knowledge(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE,
        KnowerType.NPC, npc_id, KnowerType.PLAYER, logan.id,
    )

    assert propagated is False
