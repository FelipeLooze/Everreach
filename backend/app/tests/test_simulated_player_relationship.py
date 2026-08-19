from app.db.models.relationship import (
    CharacterSimulatedPlayerRelationship,
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