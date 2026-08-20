import json

import pytest

from app.core.enums import (
    AttributeEvidenceSource,
    CharacterAttributeKey,
    CharacterXPSource,
    EventType,
)
from app.db.models.attribute import AttributeEvidenceRecord
from app.db.models.character import CharacterAttribute
from app.db.models.event import WorldEvent
from app.game import dice
from app.game.attributes.service import (
    attribute_check_modifier,
    award_attribute_development,
    get_character_attribute,
    list_character_attributes,
)
from app.game.character.service import create_character
from app.game.combat.service import resolve_skill_check
from app.game.professions.service import award_profession_xp
from app.game.progression.service import award_character_xp, xp_to_next_level
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session, name: str = "Hero"):
    campaign = create_campaign(db_session, f"Attribute Test {name}")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        name,
        region.id,
        location.id,
    )
    return campaign, character


def test_new_character_has_six_stable_attributes_in_portuguese(db_session):
    _campaign, character = _character(db_session)

    attributes = list_character_attributes(db_session, character.id)

    assert {attribute.key for attribute in attributes} == {
        key.value for key in CharacterAttributeKey
    }
    assert {attribute.definition.name for attribute in attributes} == {
        "Força",
        "Agilidade",
        "Vitalidade",
        "Inteligência",
        "Sabedoria",
        "Resistência",
    }
    assert {attribute.value for attribute in attributes} == {10}
    assert {attribute.development for attribute in attributes} == {0.0}


def test_attribute_evidence_is_authoritative_and_repetition_diminishes(db_session):
    campaign, character = _character(db_session)

    first = award_attribute_development(
        db_session,
        campaign.id,
        character,
        attribute_key=CharacterAttributeKey.STRENGTH,
        source=AttributeEvidenceSource.TRAINING,
        evidence_key="heavy-lift-form",
        context_key="training-yard",
        amount=4.0,
    )
    repeated = award_attribute_development(
        db_session,
        campaign.id,
        character,
        attribute_key=CharacterAttributeKey.STRENGTH,
        source=AttributeEvidenceSource.TRAINING,
        evidence_key="heavy-lift-form",
        context_key="training-yard",
        amount=4.0,
    )

    assert first.repetition_multiplier == 1.0
    assert repeated.repetition_multiplier == 0.5
    assert repeated.record.awarded_amount == 2.0
    assert repeated.attribute.development == 6.0
    assert repeated.attribute.value == 10


def test_real_development_increases_only_relevant_attribute(db_session):
    campaign, character = _character(db_session)

    result = award_attribute_development(
        db_session,
        campaign.id,
        character,
        attribute_key=CharacterAttributeKey.STRENGTH,
        source=AttributeEvidenceSource.PHYSICAL_EXERTION,
        evidence_key="first-stone-haul",
        context_key="real-work",
        amount=10.0,
    )

    assert result.increases == 1
    assert result.attribute.value == 11
    assert character.level == 0
    assert get_character_attribute(
        db_session, character.id, CharacterAttributeKey.AGILITY
    ).value == 10
    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.PLAYER_ATTRIBUTE_INCREASED.value
        )
        .one()
    )
    payload = json.loads(event.payload_json)
    assert payload == {
        "attribute_key": "STRENGTH",
        "attribute_name": "Força",
        "previous_value": 10,
        "new_value": 11,
    }


def test_irrelevant_evidence_source_cannot_train_attribute(db_session):
    campaign, character = _character(db_session)

    with pytest.raises(ValueError, match="not relevant"):
        award_attribute_development(
            db_session,
            campaign.id,
            character,
            attribute_key=CharacterAttributeKey.STRENGTH,
            source=AttributeEvidenceSource.MENTAL_STUDY,
            evidence_key="read-about-weightlifting",
            context_key="library",
            amount=10.0,
        )

    strength = get_character_attribute(
        db_session, character.id, CharacterAttributeKey.STRENGTH
    )
    assert strength.value == 10
    assert strength.development == 0.0


def test_character_level_does_not_increase_attributes(db_session):
    campaign, character = _character(db_session)
    before = {
        attribute.key: attribute.value
        for attribute in list_character_attributes(db_session, character.id)
    }

    award_character_xp(
        db_session,
        campaign.id,
        character,
        xp_to_next_level(0),
        source=CharacterXPSource.SIGNIFICANT_CHALLENGE,
        experience_key="challenge:attribute-independence",
    )

    after = {
        attribute.key: attribute.value
        for attribute in list_character_attributes(db_session, character.id)
    }
    assert character.level == 1
    assert after == before


def test_high_intelligence_does_not_increase_profession_xp(db_session):
    campaign, first = _character(db_session, "Scholar")
    region = first.region_id
    location = first.location_id
    second = create_character(
        db_session,
        campaign.id,
        "Cook",
        region,
        location,
    )
    get_character_attribute(
        db_session, first.id, CharacterAttributeKey.INTELLIGENCE
    ).value = 30

    first_profession = award_profession_xp(
        db_session,
        campaign.id,
        first,
        profession_key="COOKING",
        profession_name="Culinária",
        amount=0.5,
    )
    second_profession = award_profession_xp(
        db_session,
        campaign.id,
        second,
        profession_key="COOKING",
        profession_name="Culinária",
        amount=0.5,
    )

    assert first_profession is not None
    assert second_profession is not None
    assert first_profession.xp == second_profession.xp == 0.5


def test_skill_check_uses_attribute_only_when_approach_selects_it(
    db_session,
    monkeypatch,
):
    _campaign, character = _character(db_session)
    agility = get_character_attribute(
        db_session, character.id, CharacterAttributeKey.AGILITY
    )
    agility.value = 14

    monkeypatch.setattr(
        dice,
        "d20",
        lambda modifier=0: dice.RollResult(
            sides=20,
            raw=10,
            modifier=modifier,
        ),
    )
    without_attribute = resolve_skill_check(
        db_session,
        character.id,
        "Acrobacia",
    )
    with_agility = resolve_skill_check(
        db_session,
        character.id,
        "Acrobacia",
        attribute_key=CharacterAttributeKey.AGILITY,
    )

    assert attribute_check_modifier(14) == 2
    assert without_attribute.attribute_key is None
    assert without_attribute.roll.modifier == 0
    assert with_agility.attribute_key == "AGILITY"
    assert with_agility.attribute_modifier == 2
    assert with_agility.roll.modifier == 2


def test_character_sheet_hides_internal_attribute_development(
    client,
    db_session,
):
    campaign, character = _character(db_session)
    award_attribute_development(
        db_session,
        campaign.id,
        character,
        attribute_key=CharacterAttributeKey.WISDOM,
        source=AttributeEvidenceSource.PERCEPTIVE_EXPERIENCE,
        evidence_key="read-forest-signs",
        context_key="wilderness",
        amount=3.0,
    )
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/character",
        params={"character_id": character.id},
    )

    assert response.status_code == 200
    attributes = response.json()["attributes"]
    assert {row["key"] for row in attributes} == {
        key.value for key in CharacterAttributeKey
    }
    assert all("development" not in row for row in attributes)
    assert all(set(row) == {"key", "name", "value"} for row in attributes)


def test_campaign_reset_removes_hidden_attribute_evidence(db_session):
    campaign, character = _character(db_session)
    award_attribute_development(
        db_session,
        campaign.id,
        character,
        attribute_key=CharacterAttributeKey.ENDURANCE,
        source=AttributeEvidenceSource.PHYSICAL_EXERTION,
        evidence_key="long-march",
        context_key="travel",
        amount=2.0,
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(AttributeEvidenceRecord).count() == 0
    assert db_session.query(CharacterAttribute).count() == 0
