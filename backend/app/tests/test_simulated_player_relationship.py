from app.db.models.relationship import (
    CharacterSimulatedPlayerRelationship,
)
from app.core.enums import EventType
from app.db.models.event import WorldEvent
from app.game.relationships.service import (
    get_character_simulated_player_relationship,
    record_simulated_player_interaction,
    simulated_player_relationship_behavior_guidance,
)
from app.game.character.service import create_character
from app.game.players.service import (
    simulated_players_at_location,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)


def test_character_simulated_player_relationship_persists(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Relationship",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    transported = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    relationship = CharacterSimulatedPlayerRelationship(
        campaign_id=campaign.id,
        character_id=character.id,
        simulated_player_id=transported.id,
    )

    db_session.add(relationship)
    db_session.flush()

    persisted = (
        db_session.query(
            CharacterSimulatedPlayerRelationship
        )
        .filter(
            CharacterSimulatedPlayerRelationship.character_id
            == character.id,
            CharacterSimulatedPlayerRelationship.simulated_player_id
            == transported.id,
        )
        .one()
    )

    assert persisted.id == relationship.id
    assert persisted.campaign_id == campaign.id
    assert persisted.character_id == character.id
    assert persisted.simulated_player_id == transported.id
    assert persisted.familiarity == 0
    assert persisted.trust == 0
    assert persisted.affinity == 0
    assert persisted.last_interaction_minute == 0
    assert persisted.updated_at is not None

def test_record_simulated_player_interaction_creates_relationship(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Relationship Service",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    transported = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    relationship = record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        transported.id,
    )

    persisted = (
        get_character_simulated_player_relationship(
            db_session,
            campaign.id,
            character.id,
            transported.id,
        )
    )

    assert persisted is not None
    assert persisted.id == relationship.id
    assert persisted.familiarity == 1
    assert persisted.trust == 0
    assert persisted.affinity == 0

def test_simulated_player_relationship_accumulates_interactions(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Relationship Accumulation",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    transported = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        transported.id,
    )

    relationship = record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        transported.id,
        familiarity_delta=2,
        trust_delta=5,
        affinity_delta=-3,
    )

    assert relationship.familiarity == 3
    assert relationship.trust == 5
    assert relationship.affinity == -3

def test_simulated_player_relationship_values_are_bounded(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Relationship Bounds",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    transported = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    relationship = record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        transported.id,
        familiarity_delta=500,
        trust_delta=500,
        affinity_delta=-500,
    )

    assert relationship.familiarity == 100
    assert relationship.trust == 100
    assert relationship.affinity == -100

    relationship = record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        transported.id,
        familiarity_delta=-500,
        trust_delta=-500,
        affinity_delta=500,
    )

    assert relationship.familiarity == 0
    assert relationship.trust == -100
    assert relationship.affinity == 100

def test_simulated_player_relationship_change_is_evented(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Relationship Event",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    transported = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        transported.id,
        familiarity_delta=2,
        trust_delta=4,
        affinity_delta=-1,
    )

    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type
            == EventType.RELATIONSHIP_CHANGED.value,
            WorldEvent.actor_id == character.id,
        )
        .one()
    )

    assert event.importance == 2
    assert (
        '"simulated_player_id"'
        in event.payload_json
    )
    assert transported.id in event.payload_json

def test_simulated_player_relationship_behavior_guidance(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Relationship Behavior",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    transported = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    relationship = record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        transported.id,
        trust_delta=60,
        affinity_delta=-60,
    )

    trust_guidance, affinity_guidance = (
        simulated_player_relationship_behavior_guidance(
            relationship
        )
    )

    assert "Strong trust" in trust_guidance
    assert "Strong negative affinity" in affinity_guidance

    assert "personality" in trust_guidance
    assert "without forcing hostility" in affinity_guidance