"""Phase 17J — Frontiers."""

from app.core.enums import GeographicKnowledgeAspect, KnowerType, PopulationDensity
from app.db.models.subregion import Subregion
from app.game.character.service import create_character
from app.game.exploration.frontiers import assess_frontier_status
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.world.seed import create_campaign, seed_initial_region


def _pick_subregion(db_session, region_id):
    return db_session.query(Subregion).filter(Subregion.region_id == region_id, Subregion.order_index == 2).one()


def test_sparse_and_unfamiliar_is_frontier(db_session):
    campaign = create_campaign(db_session, "Fronteira Desconhecida", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region_id=region.id)
    subregion = _pick_subregion(db_session, region.id)
    subregion.population_density = PopulationDensity.SPARSE.value
    db_session.flush()

    assessment = assess_frontier_status(db_session, campaign.id, KnowerType.PLAYER, logan.id, subregion)

    assert assessment.is_frontier is True
    assert assessment.sparse_settlement is True


def test_dense_settlement_is_never_frontier_even_if_unknown(db_session):
    campaign = create_campaign(db_session, "Cidade Nao E Fronteira", world_seed=2)
    region, _village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region_id=region.id)
    subregion = _pick_subregion(db_session, region.id)
    subregion.population_density = PopulationDensity.DENSE.value
    db_session.flush()

    assessment = assess_frontier_status(db_session, campaign.id, KnowerType.PLAYER, logan.id, subregion)

    assert assessment.is_frontier is False


def test_a_familiar_knower_never_sees_it_as_frontier_even_if_sparse(db_session):
    campaign = create_campaign(db_session, "Familiar Nao E Fronteira", world_seed=3)
    region, _village = seed_initial_region(db_session, campaign.id)
    hunter_id = "npc_hunter_frontier_test"
    subregion = _pick_subregion(db_session, region.id)
    subregion.population_density = PopulationDensity.SPARSE.value
    db_session.flush()

    for aspect, statement in [
        (GeographicKnowledgeAspect.EXISTENCE, "A floresta se estende ao norte."),
        (GeographicKnowledgeAspect.DANGERS, "Lobos são comuns perto do riacho."),
        (GeographicKnowledgeAspect.DESCRIPTION, "Trilhas de caça cruzam toda a área."),
    ]:
        ensure_geographic_fact(db_session, campaign.id, "subregion", subregion.id, aspect, statement)
        grant_geographic_knowledge(
            db_session, campaign.id, KnowerType.NPC, hunter_id, "subregion", subregion.id, aspect,
        )

    assessment = assess_frontier_status(db_session, campaign.id, KnowerType.NPC, hunter_id, subregion)

    assert assessment.is_frontier is False
    assert assessment.sparse_settlement is True


def test_frontier_status_is_relative_between_two_knowers(db_session):
    """The same Subregion: frontier to the protagonist, homeland to the
    hunter who knows it well (spec's own example)."""
    campaign = create_campaign(db_session, "Fronteira Relativa", world_seed=4)
    region, _village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region_id=region.id)
    hunter_id = "npc_hunter_relative_test"
    subregion = _pick_subregion(db_session, region.id)
    subregion.population_density = PopulationDensity.SPARSE.value
    db_session.flush()

    for aspect, statement in [
        (GeographicKnowledgeAspect.EXISTENCE, "A floresta se estende ao norte."),
        (GeographicKnowledgeAspect.DANGERS, "Lobos são comuns perto do riacho."),
    ]:
        ensure_geographic_fact(db_session, campaign.id, "subregion", subregion.id, aspect, statement)
        grant_geographic_knowledge(
            db_session, campaign.id, KnowerType.NPC, hunter_id, "subregion", subregion.id, aspect,
        )

    hunter_assessment = assess_frontier_status(db_session, campaign.id, KnowerType.NPC, hunter_id, subregion)
    logan_assessment = assess_frontier_status(db_session, campaign.id, KnowerType.PLAYER, logan.id, subregion)

    assert hunter_assessment.is_frontier is False
    assert logan_assessment.is_frontier is True
