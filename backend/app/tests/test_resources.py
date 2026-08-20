import pytest

from app.core.enums import (
    AttributeEvidenceSource,
    CharacterAttributeKey,
    CharacterResourceKey,
    ResourceGrowthSource,
)
from app.db.models.resource import (
    CharacterResourceGrowth,
    ResourceGrowthEvidenceRecord,
)
from app.db.models.simulated_player import SimulatedPlayer
from app.game.attributes.service import (
    award_attribute_development,
    get_character_attribute,
)
from app.game.character.service import create_character
from app.game.combat.service import resolve_skill_check
from app.game.resources.service import (
    award_resource_development,
    get_resource_growth,
)
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session):
    campaign = create_campaign(db_session, "Resource Growth Test")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    return campaign, character


def test_luck_exists_only_in_player_character_attribute_system(db_session):
    _campaign, character = _character(db_session)

    luck = get_character_attribute(
        db_session,
        character.id,
        CharacterAttributeKey.LUCK,
    )

    assert luck.value == 10
    assert luck.definition.name == "Sorte"
    assert not hasattr(SimulatedPlayer, "attributes")


def test_luck_is_reserved_for_future_loot_and_cannot_be_routinely_trained(
    db_session,
):
    campaign, character = _character(db_session)

    with pytest.raises(ValueError, match="ordinary training"):
        award_attribute_development(
            db_session,
            campaign.id,
            character,
            attribute_key=CharacterAttributeKey.LUCK,
            source=AttributeEvidenceSource.TRAINING,
            evidence_key="repeat-dice-roll",
            context_key="routine",
            amount=10.0,
        )
    with pytest.raises(ValueError, match="cannot replace"):
        resolve_skill_check(
            db_session,
            character.id,
            "Atletismo",
            attribute_key=CharacterAttributeKey.LUCK,
        )


def test_vitality_growth_increases_hp_without_character_level(db_session):
    campaign, character = _character(db_session)

    award = award_attribute_development(
        db_session,
        campaign.id,
        character,
        attribute_key=CharacterAttributeKey.VITALITY,
        source=AttributeEvidenceSource.PHYSICAL_EXERTION,
        evidence_key="survived-first-hard-conditioning",
        context_key="training",
        amount=10.0,
    )

    assert award.attribute.value == 11
    assert character.level == 0
    assert character.hp_max == 21.0
    assert character.hp_current == 21.0
    assert character.mana_max == 10.0
    assert character.stamina_max == 20.0


def test_resource_max_growth_does_not_heal_existing_injury(db_session):
    campaign, character = _character(db_session)
    character.hp_current = 7.0

    award_attribute_development(
        db_session,
        campaign.id,
        character,
        attribute_key=CharacterAttributeKey.VITALITY,
        source=AttributeEvidenceSource.REAL_CHALLENGE,
        evidence_key="endured-serious-hardship",
        context_key="wilderness",
        amount=10.0,
    )

    assert character.hp_max == 21.0
    assert character.hp_current == 7.0


def test_endurance_growth_increases_stamina_but_intelligence_does_not_add_mana(
    db_session,
):
    campaign, character = _character(db_session)

    award_attribute_development(
        db_session,
        campaign.id,
        character,
        attribute_key=CharacterAttributeKey.ENDURANCE,
        source=AttributeEvidenceSource.PHYSICAL_EXERTION,
        evidence_key="first-endurance-march",
        context_key="travel",
        amount=10.0,
    )
    award_attribute_development(
        db_session,
        campaign.id,
        character,
        attribute_key=CharacterAttributeKey.INTELLIGENCE,
        source=AttributeEvidenceSource.MENTAL_STUDY,
        evidence_key="complex-rune-analysis",
        context_key="study",
        amount=10.0,
    )

    assert character.stamina_max == 21.0
    assert character.stamina_current == 21.0
    assert character.mana_max == 10.0


def test_real_magical_practice_can_grow_mana_independently(db_session):
    campaign, character = _character(db_session)
    attributes_before = {
        key: get_character_attribute(db_session, character.id, key).value
        for key in CharacterAttributeKey
    }

    result = award_resource_development(
        db_session,
        campaign.id,
        character,
        resource_key=CharacterResourceKey.MANA,
        source=ResourceGrowthSource.MAGICAL_PRACTICE,
        evidence_key="first-sustained-mana-shaping",
        context_key="supervised-practice",
        amount=12.5,
    )

    assert result.increases == 1
    assert character.mana_max == 11.0
    assert character.mana_current == 11.0
    assert character.level == 0
    assert {
        key: get_character_attribute(db_session, character.id, key).value
        for key in CharacterAttributeKey
    } == attributes_before


def test_resource_growth_validates_source_and_attribute_relationship(db_session):
    campaign, character = _character(db_session)

    with pytest.raises(ValueError, match="not relevant"):
        award_resource_development(
            db_session,
            campaign.id,
            character,
            resource_key=CharacterResourceKey.MANA,
            source=ResourceGrowthSource.PHYSICAL_CONDITIONING,
            evidence_key="push-ups",
            context_key="yard",
            amount=100.0,
        )
    with pytest.raises(ValueError, match="not relevant"):
        award_resource_development(
            db_session,
            campaign.id,
            character,
            resource_key=CharacterResourceKey.HP,
            source=ResourceGrowthSource.ATTRIBUTE_DEVELOPMENT,
            contributing_attribute_key=CharacterAttributeKey.INTELLIGENCE,
            evidence_key="intelligence-eleven",
            context_key="attribute-development",
            amount=10.0,
        )

    assert character.hp_max == 20.0
    assert character.mana_max == 10.0


def test_repeated_resource_exertion_has_diminishing_returns(db_session):
    campaign, character = _character(db_session)

    first = award_resource_development(
        db_session,
        campaign.id,
        character,
        resource_key=CharacterResourceKey.STAMINA,
        source=ResourceGrowthSource.RESOURCE_EXERTION,
        evidence_key="same-short-run",
        context_key="routine",
        amount=4.0,
    )
    repeated = award_resource_development(
        db_session,
        campaign.id,
        character,
        resource_key=CharacterResourceKey.STAMINA,
        source=ResourceGrowthSource.RESOURCE_EXERTION,
        evidence_key="same-short-run",
        context_key="routine",
        amount=4.0,
    )

    assert first.repetition_multiplier == 1.0
    assert repeated.repetition_multiplier == 0.5
    assert repeated.record.awarded_amount == 2.0
    assert repeated.growth.development == 6.0
    assert character.stamina_max == 20.0


def test_resource_growth_state_is_hidden_from_character_sheet(
    client,
    db_session,
):
    campaign, character = _character(db_session)
    award_resource_development(
        db_session,
        campaign.id,
        character,
        resource_key=CharacterResourceKey.MANA,
        source=ResourceGrowthSource.MAGICAL_PRACTICE,
        evidence_key="small-mana-practice",
        context_key="training",
        amount=2.0,
    )
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/character",
        params={"character_id": character.id},
    )

    assert response.status_code == 200
    character_payload = response.json()["character"]
    assert character_payload["mana_max"] == 10.0
    assert "resource_growth" not in character_payload
    assert "mana_development" not in character_payload


def test_campaign_reset_removes_resource_growth_state(db_session):
    campaign, character = _character(db_session)
    award_resource_development(
        db_session,
        campaign.id,
        character,
        resource_key=CharacterResourceKey.STAMINA,
        source=ResourceGrowthSource.RESOURCE_EXERTION,
        evidence_key="long-run",
        context_key="training",
        amount=2.0,
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CharacterResourceGrowth).count() == 0
    assert db_session.query(ResourceGrowthEvidenceRecord).count() == 0
    assert get_resource_growth(
        db_session,
        character.id,
        CharacterResourceKey.STAMINA,
    ) is None
