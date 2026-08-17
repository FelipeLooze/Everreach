import pytest

from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.travel.service import TravelError, move_character
from app.game.world.seed import create_campaign, seed_initial_region


def test_move_character_follows_valid_connection(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()

    forest = db_session.query(Location).filter(Location.region_id == region.id, Location.type == "forest").first()

    minutes = move_character(db_session, campaign.id, character, forest.id)

    assert minutes > 0
    assert character.location_id == forest.id
    assert character.region_id == region.id


def test_move_character_rejects_unconnected_location(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()

    clearing = db_session.query(Location).filter(Location.region_id == region.id, Location.name == "Clareira do Vidro Antigo").first()

    with pytest.raises(TravelError):
        move_character(db_session, campaign.id, character, clearing.id)
