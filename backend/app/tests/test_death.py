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


def test_a_fallen_character_wakes_up_instead_of_being_stuck(db_session, fake_llm):
    """Before fainting existed (2026-10-24) a fallen character could never
    act again; now the next action wakes them up back in the village."""
    campaign = create_campaign(db_session, "Critical Campaign")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    character.status = CharacterStatus.INCAPACITATED.value
    character.hp_current = 0
    db_session.flush()

    result = engine.resolve_action(db_session, fake_llm, campaign.id, character.id, "Eu me levanto")

    assert character.status == CharacterStatus.ALIVE.value and character.hp_current > 0
    assert "acorda" in result.mechanical_summary
