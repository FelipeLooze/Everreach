from app.core.enums import KnowledgeCertainty, KnowerType
from app.db.models.knowledge import KnowledgeFact
from app.game.npcs.service import known_facts, knows, teach_fact
from app.game.world.seed import create_campaign
from sqlalchemy.exc import IntegrityError
import pytest


def test_npc_does_not_know_fact_by_default(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    fact = KnowledgeFact(campaign_id=campaign.id, fact_key="king_is_dead", statement="The king is dead.")
    db_session.add(fact)
    db_session.commit()

    assert knows(db_session, KnowerType.NPC, "npc_someone", "king_is_dead", campaign.id) is False


def test_npc_knows_fact_once_taught(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    fact = KnowledgeFact(campaign_id=campaign.id, fact_key="king_is_dead", statement="The king is dead.")
    db_session.add(fact)
    db_session.commit()

    teach_fact(db_session, campaign.id, "king_is_dead", KnowerType.NPC, "npc_mira")
    db_session.commit()

    assert knows(db_session, KnowerType.NPC, "npc_mira", "king_is_dead", campaign.id) is True
    assert knows(db_session, KnowerType.NPC, "npc_other", "king_is_dead", campaign.id) is False


def test_unknown_fact_key_is_never_known(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    db_session.commit()

    assert knows(db_session, KnowerType.PLAYER, "char_1", "nonexistent_fact", campaign.id) is False


def test_knowledge_keeps_source_certainty_and_subject_per_knower(db_session):
    campaign = create_campaign(db_session, "Knowledge Metadata")
    fact = KnowledgeFact(
        campaign_id=campaign.id,
        subject="location:ruins",
        fact_key="possible_ruins",
        statement="Pode haver ruínas sob a colina.",
    )
    db_session.add(fact)
    db_session.flush()

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        "npc_osgar",
        source="relato de viajante",
        certainty=KnowledgeCertainty.RUMOR,
    )
    db_session.commit()

    npc_facts = known_facts(db_session, campaign.id, KnowerType.NPC, "npc_osgar")
    assert len(npc_facts) == 1
    assert npc_facts[0].subject == "location:ruins"
    assert npc_facts[0].source == "relato de viajante"
    assert npc_facts[0].certainty == KnowledgeCertainty.RUMOR
    assert npc_facts[0].discovered_at is not None
    assert known_facts(db_session, campaign.id, KnowerType.PLAYER, "char_other") == []


def test_fact_key_is_unique_inside_each_campaign(db_session):
    campaign = create_campaign(db_session, "Canonical Identity")
    db_session.add_all(
        [
            KnowledgeFact(
                campaign_id=campaign.id,
                fact_key="same_fact",
                statement="Primeira versão.",
            ),
            KnowledgeFact(
                campaign_id=campaign.id,
                fact_key="same_fact",
                statement="Versão conflitante.",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_teaching_the_same_fact_twice_is_idempotent(db_session):
    campaign = create_campaign(db_session, "Idempotent Knowledge")
    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="stable_fact",
        statement="Um fato estável.",
    )
    db_session.add(fact)
    db_session.flush()

    teach_fact(db_session, campaign.id, fact.fact_key, KnowerType.NPC, "npc_one")
    teach_fact(db_session, campaign.id, fact.fact_key, KnowerType.NPC, "npc_one")
    db_session.commit()

    assert len(known_facts(db_session, campaign.id, KnowerType.NPC, "npc_one")) == 1
