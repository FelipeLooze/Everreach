"""Phase 17A — Geographic Knowledge Foundation."""

import pytest

from app.core.enums import GeographicKnowledgeAspect, KnowerType, KnowledgeCertainty
from app.db.models.knowledge import KnowledgeFact
from app.db.models.subregion import Subregion
from app.game.character.service import create_character
from app.game.knowledge.geography import (
    ensure_geographic_fact,
    geographic_fact_key,
    geographic_subject,
    grant_geographic_knowledge,
    known_geographic_aspects,
    knows_geographic_aspect,
)
from app.game.world.seed import create_campaign, seed_initial_region


def test_fact_key_and_subject_format():
    assert geographic_subject("subregion", "sub_123") == "subregion:sub_123"
    assert (
        geographic_fact_key("subregion", "sub_123", GeographicKnowledgeAspect.EXISTENCE)
        == "subregion:sub_123:existence"
    )


def test_ensure_geographic_fact_is_idempotent(db_session):
    campaign = create_campaign(db_session, "Fundacao Geografica", world_seed=1)

    first = ensure_geographic_fact(
        db_session, campaign.id, "subregion", "sub_x", GeographicKnowledgeAspect.EXISTENCE,
        "Há terras a nordeste ainda não mapeadas.",
    )
    second = ensure_geographic_fact(
        db_session, campaign.id, "subregion", "sub_x", GeographicKnowledgeAspect.EXISTENCE,
        "Um texto diferente, ignorado pois o fato já existe.",
    )

    assert first.id == second.id
    count = (
        db_session.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign.id, KnowledgeFact.fact_key == first.fact_key)
        .count()
    )
    assert count == 1


def test_granting_an_unestablished_aspect_raises(db_session):
    campaign = create_campaign(db_session, "Fato Nao Existe", world_seed=2)
    character = create_character(db_session, campaign.id, "Logan")

    with pytest.raises(ValueError):
        grant_geographic_knowledge(
            db_session, campaign.id, KnowerType.PLAYER, character.id,
            "subregion", "sub_never_created", GeographicKnowledgeAspect.EXISTENCE,
        )


def test_knowledge_is_character_specific(db_session):
    campaign = create_campaign(db_session, "Conhecimento Individual", world_seed=3)
    logan = create_character(db_session, campaign.id, "Logan")
    npc_id = "npc_hunter_test"

    ensure_geographic_fact(
        db_session, campaign.id, "subregion", "sub_y", GeographicKnowledgeAspect.EXISTENCE,
        "Uma floresta densa se estende a oeste.",
    )

    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.NPC, npc_id,
        "subregion", "sub_y", GeographicKnowledgeAspect.EXISTENCE,
    )

    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.NPC, npc_id, "subregion", "sub_y", GeographicKnowledgeAspect.EXISTENCE
    ) is True
    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "subregion", "sub_y", GeographicKnowledgeAspect.EXISTENCE
    ) is False


def test_known_geographic_aspects_accumulates_and_stays_scoped(db_session):
    campaign = create_campaign(db_session, "Aspectos Acumulados", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")

    for aspect, statement in [
        (GeographicKnowledgeAspect.EXISTENCE, "Uma grande cidade existe ao sul."),
        (GeographicKnowledgeAspect.NAME, "Essa cidade é chamada de Arven."),
        (GeographicKnowledgeAspect.DIRECTION, "Fica ao sul de Cardal."),
    ]:
        ensure_geographic_fact(db_session, campaign.id, "settlement", "loc_arven", aspect, statement)

    assert known_geographic_aspects(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven"
    ) == set()

    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE,
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "settlement", "loc_arven", GeographicKnowledgeAspect.NAME,
    )

    assert known_geographic_aspects(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven"
    ) == {GeographicKnowledgeAspect.EXISTENCE, GeographicKnowledgeAspect.NAME}


def test_aspects_of_the_same_entity_share_one_subject_for_scene_matching(db_session):
    campaign = create_campaign(db_session, "Subject Compartilhado", world_seed=5)

    existence_fact = ensure_geographic_fact(
        db_session, campaign.id, "location", "loc_z", GeographicKnowledgeAspect.EXISTENCE, "Existe algo ali.",
    )
    name_fact = ensure_geographic_fact(
        db_session, campaign.id, "location", "loc_z", GeographicKnowledgeAspect.NAME, "Chama-se Vale Z.",
    )

    assert existence_fact.subject == name_fact.subject == "location:loc_z"
    assert existence_fact.fact_key != name_fact.fact_key


def test_certainty_upgrade_only_still_applies_through_the_wrapper(db_session):
    campaign = create_campaign(db_session, "Certeza Monotonica", world_seed=6)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "boundary", "bound_x", GeographicKnowledgeAspect.EXISTENCE,
        "Rumores falam de uma passagem nas montanhas.",
    )

    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "boundary", "bound_x", GeographicKnowledgeAspect.EXISTENCE,
        certainty=KnowledgeCertainty.CONFIRMED,
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "boundary", "bound_x", GeographicKnowledgeAspect.EXISTENCE,
        certainty=KnowledgeCertainty.RUMOR,
    )

    from app.db.models.knowledge import KnowledgeKnower

    fact_key = geographic_fact_key("boundary", "bound_x", GeographicKnowledgeAspect.EXISTENCE)
    fact = db_session.query(KnowledgeFact).filter(KnowledgeFact.fact_key == fact_key).one()
    knower = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == logan.id,
        )
        .one()
    )
    assert knower.certainty == KnowledgeCertainty.CONFIRMED.value


def test_closes_the_real_gap_for_a_generated_subregion(db_session):
    """Subregion had zero Knowledge integration before 17A (confirmed by
    audit) — prove the primitives work end-to-end against a real,
    procedurally generated Subregion, not just a synthetic id."""
    campaign = create_campaign(db_session, "Subregiao Real", world_seed=7)
    region, _village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region_id=region.id)

    far_subregion = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == region.id, Subregion.order_index == 3)
        .one()
    )

    ensure_geographic_fact(
        db_session, campaign.id, "subregion", far_subregion.id, GeographicKnowledgeAspect.EXISTENCE,
        f"Há uma área conhecida como {far_subregion.name} em algum lugar da região.",
    )

    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "subregion", far_subregion.id, GeographicKnowledgeAspect.EXISTENCE,
    ) is False

    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "subregion", far_subregion.id, GeographicKnowledgeAspect.EXISTENCE,
        source="conversa com um viajante",
    )

    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "subregion", far_subregion.id, GeographicKnowledgeAspect.EXISTENCE,
    ) is True
