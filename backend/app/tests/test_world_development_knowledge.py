from app.core.enums import (
    KnowerType,
    WorldDevelopmentType,
)
from app.db.models.knowledge import (
    KnowledgeFact,
    KnowledgeKnower,
)
from app.game.developments.service import (
    create_world_development,
)
from app.game.npcs.service import knows
from app.game.time.clock import advance_world_time
from app.game.world.seed import create_campaign
from app.simulation import development_simulation


def test_world_development_creation_creates_unknown_world_fact(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Knowledge",
    )

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Nova ponte",
        interval_minutes=7 * 24 * 60,
        payload={
            "progress": 0,
            "progress_per_update": 10,
        },
    )

    facts = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.subject
            == f"world_development:{development.id}"
        )
        .all()
    )

    assert len(facts) == 1
    assert facts[0].statement == "Nova ponte começou."

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id
            == facts[0].id
        )
        .count()
        == 0
    )


def test_construction_progress_creates_separate_immutable_facts(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Progress Knowledge",
    )

    interval = 7 * 24 * 60

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Estrada do vale",
        interval_minutes=interval,
        payload={
            "progress": 0,
            "progress_per_update": 10,
        },
    )

    advance_world_time(
        db_session,
        campaign.id,
        2 * interval,
    )

    development_simulation.tick(
        db_session,
        campaign.id,
        2 * interval,
    )

    db_session.flush()

    facts = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.subject
            == f"world_development:{development.id}"
        )
        .order_by(KnowledgeFact.fact_key)
        .all()
    )

    statements = {
        fact.statement
        for fact in facts
    }

    assert statements == {
        "Estrada do vale começou.",
        "Estrada do vale atingiu 10% de progresso.",
        "Estrada do vale atingiu 20% de progresso.",
    }

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id.in_(
                [fact.id for fact in facts]
            )
        )
        .count()
        == 0
    )