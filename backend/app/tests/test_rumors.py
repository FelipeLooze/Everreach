"""Phase 17C — Rumors & Geographic Information Sources."""

import pytest

from app.core.enums import GeographicKnowledgeAspect, KnowerType, KnowledgeCertainty, RumorAccuracy
from app.db.models.knowledge import KnowledgeFact
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge, knows_geographic_aspect
from app.game.knowledge.rumors import establish_rumor, grant_rumor, knows_rumor, rumor_fact_key
from app.game.world.seed import create_campaign


def test_establish_rumor_is_idempotent_and_stores_accuracy(db_session):
    campaign = create_campaign(db_session, "Rumor Idempotente", world_seed=1)

    first = establish_rumor(
        db_session, campaign.id, "boundary", "bound_x", GeographicKnowledgeAspect.ROUTE, "old_traveler",
        "Mercadores ainda usam um túnel escondido nas montanhas.",
        RumorAccuracy.OUTDATED,
    )
    second = establish_rumor(
        db_session, campaign.id, "boundary", "bound_x", GeographicKnowledgeAspect.ROUTE, "old_traveler",
        "Texto diferente, ignorado.",
        RumorAccuracy.TRUE,
    )

    assert first.id == second.id
    assert first.rumor_accuracy == RumorAccuracy.OUTDATED.value


def test_rumor_and_canonical_fact_coexist_independently(db_session):
    """The Ancient Tunnel example: Canon says the entrance collapsed;
    the rumor says merchants still use it. Both exist at once."""
    campaign = create_campaign(db_session, "Tunel Antigo", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "boundary", "bound_gray", GeographicKnowledgeAspect.ROUTE,
        "A entrada do túnel antigo desmoronou há 20 anos.",
    )
    establish_rumor(
        db_session, campaign.id, "boundary", "bound_gray", GeographicKnowledgeAspect.ROUTE, "tavern_traveler",
        "Mercadores ainda usam um túnel escondido nas montanhas.",
        RumorAccuracy.OUTDATED,
    )

    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "boundary", "bound_gray", GeographicKnowledgeAspect.ROUTE, "tavern_traveler",
        source="viajante na taverna de Cardal",
    )

    # Logan believes the rumor but was never taught the canonical fact.
    assert knows_rumor(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_gray", GeographicKnowledgeAspect.ROUTE, "tavern_traveler"
    ) is True
    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_gray", GeographicKnowledgeAspect.ROUTE
    ) is False

    canonical_fact = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.campaign_id == campaign.id,
            KnowledgeFact.fact_key == "boundary:bound_gray:route",
        )
        .one()
    )
    assert "desmoronou" in canonical_fact.statement
    assert canonical_fact.rumor_accuracy is None


def test_multiple_independent_rumors_about_the_same_aspect_coexist(db_session):
    campaign = create_campaign(db_session, "Rumores Multiplos", world_seed=3)

    establish_rumor(
        db_session, campaign.id, "boundary", "bound_y", GeographicKnowledgeAspect.DANGERS, "hunter",
        "A passagem é segura na maior parte do ano.",
        RumorAccuracy.PARTIALLY_TRUE,
    )
    establish_rumor(
        db_session, campaign.id, "boundary", "bound_y", GeographicKnowledgeAspect.DANGERS, "merchant",
        "Não entre naquela passagem, é perigosa demais.",
        RumorAccuracy.TRUE,
    )

    hunter_key = rumor_fact_key("boundary", "bound_y", GeographicKnowledgeAspect.DANGERS, "hunter")
    merchant_key = rumor_fact_key("boundary", "bound_y", GeographicKnowledgeAspect.DANGERS, "merchant")
    assert hunter_key != merchant_key

    facts = (
        db_session.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign.id, KnowledgeFact.fact_key.in_([hunter_key, merchant_key]))
        .all()
    )
    assert len(facts) == 2


def test_granting_an_unestablished_rumor_raises(db_session):
    campaign = create_campaign(db_session, "Rumor Nao Existe", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")

    with pytest.raises(ValueError):
        grant_rumor(
            db_session, campaign.id, KnowerType.PLAYER, logan.id,
            "boundary", "bound_never", GeographicKnowledgeAspect.EXISTENCE, "nobody",
            source="ninguém",
        )


def test_rumor_knowledge_is_character_specific(db_session):
    campaign = create_campaign(db_session, "Rumor Individual", world_seed=5)
    logan = create_character(db_session, campaign.id, "Logan")
    npc_id = "npc_test_hunter"

    establish_rumor(
        db_session, campaign.id, "boundary", "bound_z", GeographicKnowledgeAspect.EXISTENCE, "villager",
        "Dizem que há uma passagem oculta.",
        RumorAccuracy.MISINTERPRETED,
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.NPC, npc_id,
        "boundary", "bound_z", GeographicKnowledgeAspect.EXISTENCE, "villager",
        source="fofoca local",
    )

    assert knows_rumor(
        db_session, campaign.id, KnowerType.NPC, npc_id, "boundary", "bound_z", GeographicKnowledgeAspect.EXISTENCE, "villager"
    ) is True
    assert knows_rumor(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_z", GeographicKnowledgeAspect.EXISTENCE, "villager"
    ) is False
