import pytest

from app.core.enums import CharacterStatus
from app.game import engine
from app.game.character.service import create_character, kill_character
from app.game.world.seed import create_campaign, seed_initial_region


def test_dead_character_cannot_act(db_session, fake_llm):
    campaign = create_campaign(db_session, "Test Campaign")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()

    kill_character(db_session, campaign.id, character, cause="test")
    db_session.commit()

    assert character.status == CharacterStatus.DEAD

    with pytest.raises(engine.CharacterDeadError):
        engine.resolve_action(db_session, fake_llm, campaign.id, character.id, "I look around")


def test_death_is_permanent_status(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()

    kill_character(db_session, campaign.id, character)
    db_session.commit()

    assert character.status == "DEAD"


def test_incapacitated_character_cannot_send_world_actions(db_session, fake_llm):
    campaign = create_campaign(db_session, "Critical Campaign")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    character.status = CharacterStatus.INCAPACITATED.value
    character.hp_current = 0
    db_session.flush()

    with pytest.raises(engine.CharacterIncapacitatedError):
        engine.resolve_action(db_session, fake_llm, campaign.id, character.id, "Eu me levanto")

    assert fake_llm.calls == []
