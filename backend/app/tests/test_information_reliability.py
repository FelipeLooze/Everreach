"""Phase 17N — Information Reliability & Contradiction."""

from app.core.enums import GeographicKnowledgeAspect, KnowerType, KnowledgeCertainty, RumorAccuracy
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.knowledge.reliability import has_contradictory_information, list_known_perspectives
from app.game.knowledge.rumors import establish_rumor, grant_rumor
from app.game.world.seed import create_campaign


def test_single_known_fact_has_no_contradiction(db_session):
    campaign = create_campaign(db_session, "Sem Contradicao", world_seed=1)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "boundary", "bound_x", GeographicKnowledgeAspect.DANGERS,
        "Predadores raros foram vistos ali.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_x", GeographicKnowledgeAspect.DANGERS,
    )

    perspectives = list_known_perspectives(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_x", GeographicKnowledgeAspect.DANGERS
    )

    assert len(perspectives) == 1
    assert has_contradictory_information(perspectives) is False


def test_canonical_fact_and_a_contradicting_rumor_both_show_up(db_session):
    """Mer Gorge example: the traveler says it's safe, the world truth
    (known via a canonical fact) says otherwise."""
    campaign = create_campaign(db_session, "Garganta Contraditoria", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "boundary", "bound_gorge", GeographicKnowledgeAspect.DANGERS,
        "Um predador territorial se mudou recentemente para a garganta.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_gorge",
        GeographicKnowledgeAspect.DANGERS, certainty=KnowledgeCertainty.CONFIRMED,
    )
    establish_rumor(
        db_session, campaign.id, "boundary", "bound_gorge", GeographicKnowledgeAspect.DANGERS, "traveler_a",
        "Um viajante garante que a garganta é segura.",
        RumorAccuracy.FALSE,
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "boundary", "bound_gorge", GeographicKnowledgeAspect.DANGERS, "traveler_a",
        source="viajante na estrada",
    )

    perspectives = list_known_perspectives(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_gorge", GeographicKnowledgeAspect.DANGERS
    )

    assert len(perspectives) == 2
    assert has_contradictory_information(perspectives) is True
    # Most confidently held belief comes first.
    assert perspectives[0].certainty == KnowledgeCertainty.CONFIRMED.value


def test_two_contradicting_rumors_both_show_up(db_session):
    campaign = create_campaign(db_session, "Dois Rumores Contraditorios", world_seed=3)
    logan = create_character(db_session, campaign.id, "Logan")

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
    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_y", GeographicKnowledgeAspect.DANGERS,
        "hunter", source="caçador",
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_y", GeographicKnowledgeAspect.DANGERS,
        "merchant", source="mercador",
    )

    perspectives = list_known_perspectives(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_y", GeographicKnowledgeAspect.DANGERS
    )

    assert len(perspectives) == 2
    assert has_contradictory_information(perspectives) is True


def test_agreeing_beliefs_are_not_a_contradiction(db_session):
    campaign = create_campaign(db_session, "Rumores Concordam", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")

    establish_rumor(
        db_session, campaign.id, "boundary", "bound_z", GeographicKnowledgeAspect.DANGERS, "hunter",
        "É perigoso entrar ali.",
        RumorAccuracy.TRUE,
    )
    establish_rumor(
        db_session, campaign.id, "boundary", "bound_z", GeographicKnowledgeAspect.DANGERS, "merchant",
        "É perigoso entrar ali.",
        RumorAccuracy.TRUE,
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_z", GeographicKnowledgeAspect.DANGERS,
        "hunter", source="caçador",
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_z", GeographicKnowledgeAspect.DANGERS,
        "merchant", source="mercador",
    )

    perspectives = list_known_perspectives(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_z", GeographicKnowledgeAspect.DANGERS
    )

    assert has_contradictory_information(perspectives) is False


def test_perspectives_are_scoped_per_knower(db_session):
    campaign = create_campaign(db_session, "Perspectiva Individual", world_seed=5)
    logan = create_character(db_session, campaign.id, "Logan")
    npc_id = "npc_other_knower_test"

    establish_rumor(
        db_session, campaign.id, "boundary", "bound_w", GeographicKnowledgeAspect.DANGERS, "someone",
        "Rumor qualquer.",
        RumorAccuracy.MISINTERPRETED,
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.NPC, npc_id, "boundary", "bound_w", GeographicKnowledgeAspect.DANGERS,
        "someone", source="alguém",
    )

    logan_perspectives = list_known_perspectives(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_w", GeographicKnowledgeAspect.DANGERS
    )
    assert logan_perspectives == []
