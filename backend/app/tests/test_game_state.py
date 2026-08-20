from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.world.seed import create_campaign, seed_initial_region


def test_build_game_state_reflects_character_and_location(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()

    state = build_game_state(db_session, campaign.id, character.id)

    assert state.character.id == character.id
    assert state.region.id == region.id
    assert state.location.id == village.id
    assert state.world_time is not None
    assert state.inventory.items == ()
    assert state.inventory.encumbrance.value == "NORMAL"
    assert any(npc.name == "Osgar Vell" for npc in state.nearby_npcs)
    assert len(state.active_quests) == 0  # quest not started until API layer starts it
