import random
from app.core.enums import EventType, ActionIntentType
from app.db.models.event import WorldEvent
from app.game.players.service import (
    get_active_simulated_player_interlocutor,
    meet_simulated_player,
    select_existing_simulated_player_for_encounter,
    simulated_players_at_location,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)
from app.ai.intent_parser import Intent
from app.game import engine
from app.game.game_state import build_game_state

def test_encounter_reuses_existing_transported_person(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Existing Encounter",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    before = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert before

    before_ids = {
        player.id
        for player in before
    }

    selected = (
        select_existing_simulated_player_for_encounter(
            db_session,
            campaign.id,
            location.id,
            rng=random.Random(42),
        )
    )

    after = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert selected is not None
    assert selected.id in before_ids

    assert {
        player.id
        for player in after
    } == before_ids

def test_simulated_player_conversation_becomes_active(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Conversation",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    from app.game.character.service import (
        create_character,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Logan",
        _region.id,
        location.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert players

    player = players[0]

    met = meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    active = (
        get_active_simulated_player_interlocutor(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert met.id == player.id

    assert active is not None
    assert active.id == player.id

    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign.id,
            WorldEvent.actor_id
            == character.id,
            WorldEvent.event_type
            == EventType.PLAYER_MET_SIMULATED_PLAYER.value,
        )
        .one()
    )

    assert event is not None

def test_talk_intent_can_target_simulated_player(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Talk To Transported",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    from app.game.character.service import (
        create_character,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Logan",
        region.id,
        location.id,
    )

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    assert state.nearby_simulated_players

    transported = (
        state.nearby_simulated_players[0]
    )

    intent = Intent(
        type=ActionIntentType.TALK,
        target=transported.name,
        raw_text=(
            f"Eu falo com {transported.name}."
        ),
    )

    summary, minutes = engine._apply_intent(
        db_session,
        campaign.id,
        character,
        intent,
        state,
    )

    assert transported.name in summary
    assert minutes == 10

    active = (
        get_active_simulated_player_interlocutor(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert active is not None
    assert active.id == transported.id