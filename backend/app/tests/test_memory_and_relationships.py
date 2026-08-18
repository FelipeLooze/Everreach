import pytest

from app.core.enums import EventType, KnowerType, MemoryOwnerType
from app.db.models.event import WorldEvent
from app.db.models.knowledge import KnowledgeKnower
from app.db.models.memory import Memory
from app.db.models.npc import NPC
from app.db.models.location import Location
from app.ai.memory_manager import get_relevant_memories
from app.game.character.service import create_character
from app.game.relationships.service import record_npc_interaction
from app.game.world.seed import create_campaign, seed_initial_region
from app.game.npcs.service import (
    knows,
    propagate_fact,
    propagate_fact_locally,
)


def _scene(db_session):
    campaign = create_campaign(db_session, "Memory Test")
    region, cardal = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, cardal.id)
    db_session.commit()
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").one()
    return campaign, character, osgar


def test_explicit_knowledge_propagation_preserves_source_and_certainty(db_session):
    campaign, character, osgar = _scene(db_session)
    fact_key = "osgar_knows_cardal_east_road"
    assert not knows(db_session, KnowerType.PLAYER, character.id, fact_key, campaign.id)

    changed = propagate_fact(
        db_session,
        campaign.id,
        fact_key,
        KnowerType.NPC,
        osgar.id,
        KnowerType.PLAYER,
        character.id,
    )
    db_session.commit()

    assert changed is True
    assert knows(db_session, KnowerType.PLAYER, character.id, fact_key, campaign.id)
    link = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character.id,
        )
        .one()
    )
    assert link.source == f"npc:{osgar.id}"
    assert link.certainty == "CONFIRMED"

    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.KNOWLEDGE_PROPAGATED.value)
        .one()
    )
    assert event.importance == 3
    player_memory = (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == MemoryOwnerType.PLAYER.value,
            Memory.owner_id == character.id,
            Memory.source_event_id == event.id,
        )
        .one()
    )
    assert "Estrada do Moinho" in player_memory.summary_text

    relevant = get_relevant_memories(
        db_session,
        campaign.id,
        MemoryOwnerType.PLAYER,
        character.id,
        subjects=[player_memory.subject],
        query_text="estrada",
    )
    assert relevant == [player_memory]
    assert (
        propagate_fact(
            db_session,
            campaign.id,
            fact_key,
            KnowerType.NPC,
            osgar.id,
            KnowerType.PLAYER,
            character.id,
        )
        is False
    )


def test_knowledge_cannot_propagate_from_an_ignorant_source(db_session):
    campaign, character, _osgar = _scene(db_session)

    with pytest.raises(ValueError, match="fonte não conhece"):
        propagate_fact(
            db_session,
            campaign.id,
            "osgar_knows_cardal_east_road",
            KnowerType.NPC,
            "npc_ignorante",
            KnowerType.PLAYER,
            character.id,
        )


def test_relevant_memory_retrieval_isolated_by_owner(db_session):
    campaign, character, _osgar = _scene(db_session)
    other = create_character(db_session, campaign.id, "Other")
    source = next(
        event
        for event in db_session.query(WorldEvent).all()
        if event.actor_id == character.id
    )
    db_session.add_all(
        [
            Memory(
                campaign_id=campaign.id,
                owner_type=MemoryOwnerType.PLAYER.value,
                owner_id=character.id,
                subject="location:cardal",
                summary_text="Hero recorda a praça de Cardal.",
                source_event_id=source.id,
                importance=3,
            ),
            Memory(
                campaign_id=campaign.id,
                owner_type=MemoryOwnerType.PLAYER.value,
                owner_id=other.id,
                subject="location:cardal",
                summary_text="Memória privada de outro personagem.",
                source_event_id=source.id,
                importance=5,
            ),
        ]
    )
    db_session.commit()

    memories = get_relevant_memories(
        db_session,
        campaign.id,
        MemoryOwnerType.PLAYER,
        character.id,
        subjects=["location:cardal"],
        query_text="Cardal",
    )

    assert len(memories) == 1
    assert memories[0].owner_id == character.id
    assert "outro personagem" not in memories[0].summary_text


def test_relationship_changes_are_bounded_and_evented(db_session):
    campaign, character, osgar = _scene(db_session)

    relationship = record_npc_interaction(
        db_session,
        campaign.id,
        character.id,
        osgar.id,
        familiarity_delta=150,
        trust_delta=7,
        affinity_delta=-4,
    )
    db_session.commit()

    assert relationship.familiarity == 100
    assert relationship.trust == 7
    assert relationship.affinity == -4
    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.RELATIONSHIP_CHANGED.value)
        .one()
    )
    assert event.importance == 2
    assert event.actor_id == character.id

def test_local_knowledge_propagation_between_people_at_same_location(
    db_session,
):
    campaign, character, osgar = _scene(
        db_session
    )

    fact_key = (
        "osgar_knows_cardal_east_road"
    )

    assert not knows(
        db_session,
        KnowerType.PLAYER,
        character.id,
        fact_key,
        campaign.id,
    )

    changed = propagate_fact_locally(
        db_session,
        campaign.id,
        fact_key,
        KnowerType.NPC,
        osgar.id,
        KnowerType.PLAYER,
        character.id,
    )

    assert changed is True

    assert knows(
        db_session,
        KnowerType.PLAYER,
        character.id,
        fact_key,
        campaign.id,
    )

def test_local_knowledge_propagation_rejects_people_at_different_locations(
    db_session,
):
    campaign, character, osgar = _scene(
        db_session
    )

    fact_key = (
        "osgar_knows_cardal_east_road"
    )

    other_location = (
        db_session.query(Location)
        .filter(
            Location.region_id
            == character.region_id,
            Location.id
            != character.location_id,
        )
        .order_by(Location.id)
        .first()
    )

    assert other_location is not None

    character.location_id = (
        other_location.id
    )

    db_session.flush()

    with pytest.raises(
        ValueError,
        match="mesmo local",
    ):
        propagate_fact_locally(
            db_session,
            campaign.id,
            fact_key,
            KnowerType.NPC,
            osgar.id,
            KnowerType.PLAYER,
            character.id,
        )

    assert not knows(
        db_session,
        KnowerType.PLAYER,
        character.id,
        fact_key,
        campaign.id,
    )

    propagated_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.KNOWLEDGE_PROPAGATED.value
        )
        .count()
    )

    assert propagated_events == 0