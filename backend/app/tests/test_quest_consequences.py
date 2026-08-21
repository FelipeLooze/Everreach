"""Phase 12E — Consequences.

A quest resolving (or not) should be able to change the world beyond
"+XP, nothing else" — but only through the real Relationships/Knowledge
systems, never a parallel one. apply_quest_consequences is a pure
delegator: it never mutates state directly, and organization/economic
consequences aren't modeled here since there's no system yet to apply
them into (Phase 13/14).
"""

from app.core.enums import KnowerType, KnowledgeCertainty, QuestSource
from app.db.models.knowledge import KnowledgeFact
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.npcs.service import knows
from app.game.quests.consequences import (
    KnowledgeConsequence,
    QuestConsequences,
    RelationshipConsequence,
    apply_quest_consequences,
)
from app.game.quests.service import abandon_quest, create_quest, fail_quest, start_quest
from app.game.relationships.service import get_character_npc_relationship
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Quest Consequences")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, character


def test_no_consequences_is_a_safe_noop(db_session):
    campaign, region, character = _setup(db_session)

    apply_quest_consequences(db_session, campaign.id, character.id, None)


def test_relationship_consequence_applies_through_the_real_relationship_service(db_session):
    campaign, region, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()

    consequences = QuestConsequences(
        relationships=(
            RelationshipConsequence(npc_id=osgar.id, trust_delta=15, affinity_delta=5),
        )
    )
    apply_quest_consequences(db_session, campaign.id, character.id, consequences)

    relationship = get_character_npc_relationship(db_session, campaign.id, character.id, osgar.id)
    assert relationship is not None
    assert relationship.trust == 15
    assert relationship.affinity == 5


def test_knowledge_consequence_teaches_a_registered_fact(db_session):
    campaign, region, character = _setup(db_session)
    fact = KnowledgeFact(
        campaign_id=campaign.id, fact_key="darven_grateful", statement="Darven owes Logan a favor."
    )
    db_session.add(fact)
    db_session.commit()

    consequences = QuestConsequences(
        knowledge=(
            KnowledgeConsequence(
                fact_key="darven_grateful",
                knower_type=KnowerType.PLAYER,
                knower_id=character.id,
                certainty=KnowledgeCertainty.CONFIRMED,
            ),
        )
    )
    apply_quest_consequences(db_session, campaign.id, character.id, consequences)

    assert knows(db_session, KnowerType.PLAYER, character.id, "darven_grateful", campaign.id) is True


def test_fail_quest_applies_its_consequences(db_session):
    campaign, region, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)
    start_quest(db_session, character.id, quest.id)

    fail_quest(
        db_session, campaign.id, character.id, quest.id,
        reason="O comboio foi emboscado.",
        consequences=QuestConsequences(
            relationships=(RelationshipConsequence(npc_id=osgar.id, trust_delta=-10),)
        ),
    )

    relationship = get_character_npc_relationship(db_session, campaign.id, character.id, osgar.id)
    assert relationship is not None and relationship.trust == -10


def test_abandon_quest_applies_its_consequences(db_session):
    campaign, region, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)
    start_quest(db_session, character.id, quest.id)

    abandon_quest(
        db_session, campaign.id, character.id, quest.id,
        consequences=QuestConsequences(
            relationships=(RelationshipConsequence(npc_id=osgar.id, trust_delta=-5),)
        ),
    )

    relationship = get_character_npc_relationship(db_session, campaign.id, character.id, osgar.id)
    assert relationship is not None and relationship.trust == -5


def test_fail_quest_without_consequences_still_works_as_before(db_session):
    campaign, region, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Escolta", source=QuestSource.NPC_REQUEST)
    start_quest(db_session, character.id, quest.id)

    cq = fail_quest(db_session, campaign.id, character.id, quest.id)

    assert cq.status == "FAILED"
