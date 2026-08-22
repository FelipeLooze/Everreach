"""Phase 16P — Historical / Canon Relationships."""

from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.game.world.boundaries import create_regional_boundary
from app.game.world.neighbor_region import materialize_neighbor_region
from app.game.world.seed import create_campaign, seed_initial_region


def test_materializing_a_neighbor_records_a_historical_relationship_fact(db_session):
    campaign = create_campaign(db_session, "Canon Cruzado", world_seed=300)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)

    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)

    fact_key = f"region_relationship:{source_region.id}:{neighbor.id}"
    fact = (
        db_session.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign.id, KnowledgeFact.fact_key == fact_key)
        .one()
    )
    assert fact.subject == f"region:{neighbor.id}"
    assert source_region.name in fact.statement


def test_no_one_is_granted_the_historical_relationship_fact_at_generation_time(db_session):
    campaign = create_campaign(db_session, "Canon Ninguem Sabe", world_seed=301)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)

    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)

    fact_key = f"region_relationship:{source_region.id}:{neighbor.id}"
    fact = (
        db_session.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign.id, KnowledgeFact.fact_key == fact_key)
        .one()
    )
    knowers = db_session.query(KnowledgeKnower).filter(KnowledgeKnower.fact_id == fact.id).all()
    assert knowers == []
