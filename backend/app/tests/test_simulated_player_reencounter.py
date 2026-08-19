from app.game.character.service import create_character
from app.core.enums import SimulatedPlayerActivity
from app.game.players.service import (
    meet_simulated_player,
    select_existing_simulated_player_for_encounter,
    select_known_simulated_player_for_reencounter,
    simulated_players_at_location,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)


def test_known_present_transportee_can_be_selected_for_reencounter(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Natural Reencounter",
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

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert len(players) >= 2

    known_player = players[0]
    unknown_player = players[1]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        known_player.id,
    )

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is not None
    assert selected.id == known_player.id
    assert selected.id != unknown_player.id

def test_known_transportee_in_transit_cannot_be_reencountered(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Blocks Reencounter",
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

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    player.travel_arrival_world_minute = 999999

    db_session.flush()

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is None

def test_unknown_present_transportee_is_not_a_reencounter(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Unknown Person Is Not Reencounter",
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

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert players

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is None

def test_resting_known_transportee_is_not_available_for_reencounter(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Resting Reencounter",
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

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    player.activity = (
        SimulatedPlayerActivity.RESTING.value
    )

    db_session.flush()

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is None

def test_working_known_transportee_can_be_reencountered(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Working Reencounter",
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

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    player.activity = (
        SimulatedPlayerActivity.WORKING.value
    )

    db_session.flush()

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is not None
    assert selected.id == player.id

def test_training_known_transportee_can_be_reencountered(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Training Reencounter",
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

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    player.activity = (
        SimulatedPlayerActivity.TRAINING.value
    )

    db_session.flush()

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is not None
    assert selected.id == player.id

def test_resting_transportees_are_not_selected_for_casual_encounter(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Resting Casual Encounter",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert players

    for player in players:
        player.activity = (
            SimulatedPlayerActivity.RESTING.value
        )

    db_session.flush()

    selected = (
        select_existing_simulated_player_for_encounter(
            db_session,
            campaign.id,
            location.id,
        )
    )

    assert selected is None