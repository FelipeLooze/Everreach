import json

import pytest

from app.core.enums import EarthProfession, EventType
from app.db.models.event import WorldEvent
from app.db.models.profession import CharacterProfession, Profession
from app.game.character.service import create_character
from app.game.professions.service import (
    award_profession_xp,
    profession_xp_to_next_level,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session):
    campaign = create_campaign(db_session, "Profession Test")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    return campaign, character


def test_new_character_has_no_profession_rows(db_session):
    _campaign, character = _character(db_session)

    assert (
        db_session.query(CharacterProfession)
        .filter(CharacterProfession.character_id == character.id)
        .count()
        == 0
    )


def test_profession_catalog_is_extensible(db_session):
    profession = Profession(
        key="CULINARY",
        name="Culinária",
        description="Preparo prático de alimentos.",
    )
    db_session.add(profession)
    db_session.flush()

    stored = db_session.get(Profession, profession.id)
    assert stored is not None
    assert stored.key == "CULINARY"


def test_first_valid_award_lazily_creates_profession_progress(db_session):
    campaign, character = _character(db_session)

    progress = award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        amount=0.1,
    )

    assert progress is not None
    assert progress.level == 0
    assert progress.xp == 0.1
    assert progress.profession.key == "HERBALISM"
    assert character.level == 0
    assert character.xp == 0

    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.PLAYER_GAINED_PROFESSION_XP.value
        )
        .one()
    )
    payload = json.loads(event.payload_json)
    assert payload["profession_key"] == "HERBALISM"
    assert payload["amount"] == 0.1
    assert payload["created"] is True


def test_award_below_initial_minimum_creates_nothing(db_session):
    campaign, character = _character(db_session)

    progress = award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        amount=0.05,
    )

    assert progress is None
    assert db_session.query(Profession).count() == 0
    assert db_session.query(CharacterProfession).count() == 0
    assert (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.PLAYER_GAINED_PROFESSION_XP.value
        )
        .count()
        == 0
    )


def test_non_finite_profession_xp_is_rejected(db_session):
    campaign, character = _character(db_session)

    with pytest.raises(ValueError, match="must be finite"):
        award_profession_xp(
            db_session,
            campaign.id,
            character,
            profession_key="HERBALISM",
            profession_name="Herbalismo",
            amount=float("nan"),
        )

    assert db_session.query(CharacterProfession).count() == 0


def test_existing_profession_preserves_sub_tenth_precision(db_session):
    campaign, character = _character(db_session)
    progress = award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="CULINARY",
        profession_name="Culinária",
        amount=0.1,
    )

    updated = award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="CULINARY",
        profession_name="Culinária",
        amount=0.01,
    )

    assert updated is progress
    assert updated is not None
    assert updated.xp == 0.11
    assert db_session.query(CharacterProfession).count() == 1


def test_profession_level_is_independent_and_carries_remainder(db_session):
    campaign, character = _character(db_session)
    amount = profession_xp_to_next_level(0) * 2 + 0.5

    progress = award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="CULINARY",
        profession_name="Culinária",
        amount=amount,
    )

    assert progress is not None
    assert progress.level == 2
    assert progress.xp == 0.5
    assert character.level == 0
    assert character.xp == 0
    transitions = [
        json.loads(event.payload_json)
        for event in db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.PLAYER_PROFESSION_LEVELED_UP.value
        )
        .all()
    ]
    assert [
        (item["previous_level"], item["new_level"])
        for item in transitions
    ] == [(0, 1), (1, 2)]


def test_character_sheet_only_returns_started_professions(
    client,
    db_session,
):
    campaign, character = _character(db_session)
    award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        amount=0.11,
    )
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/character",
        params={"character_id": character.id},
    )

    assert response.status_code == 200
    assert response.json()["professions"] == [
        {
            "key": "HERBALISM",
            "name": "Herbalismo",
            "level": 0,
            "xp": 0.11,
        }
    ]


def test_background_affinity_is_single_and_grants_only_ten_percent(
    db_session,
):
    campaign = create_campaign(db_session, "Background Affinity")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Chef",
        region.id,
        location.id,
        earth_profession=EarthProfession.CHEF,
    )

    assert character.background == "Chef profissional na Terra"
    assert character.profession_affinity_key == "CULINARY"
    assert db_session.query(CharacterProfession).count() == 0

    culinary = award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="CULINARY",
        profession_name="Culinária",
        amount=0.5,
    )
    herbalism = award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        amount=0.5,
    )

    assert culinary is not None
    assert culinary.xp == pytest.approx(0.55)
    assert herbalism is not None
    assert herbalism.xp == 0.5
    assert character.level == 0
    assert character.xp == 0

    culinary_event = next(
        json.loads(event.payload_json)
        for event in db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.PLAYER_GAINED_PROFESSION_XP.value
        )
        .all()
        if json.loads(event.payload_json)["profession_key"] == "CULINARY"
    )
    assert culinary_event["base_amount"] == 0.5
    assert culinary_event["affinity_multiplier"] == 1.1
    assert culinary_event["amount"] == pytest.approx(0.55)


def test_background_affinity_can_start_profession_after_bonus(db_session):
    campaign = create_campaign(db_session, "Affinity Lazy Creation")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Chef",
        region.id,
        location.id,
        earth_profession=EarthProfession.CHEF,
    )

    progress = award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="CULINARY",
        profession_name="Culinária",
        amount=0.095,
    )

    assert progress is not None
    assert progress.xp == pytest.approx(0.1045)


def test_character_creation_api_persists_one_background_affinity(
    client,
    db_session,
):
    campaign = create_campaign(db_session, "Affinity API")
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/characters",
        json={"name": "Lia", "earth_profession": "CARPENTER"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["background"] == "Carpinteiro profissional na Terra"
    assert body["profession_affinity_key"] == "CARPENTRY"
    assert db_session.query(CharacterProfession).count() == 0
