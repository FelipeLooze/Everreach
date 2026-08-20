import json
import pytest

from app.core.enums import CharacterXPSource, EventType
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.game.character.service import create_character
from app.game.progression.service import (
    add_xp,
    award_character_xp,
    xp_to_next_level,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)

def test_xp_requirement_grows_with_level():
    assert xp_to_next_level(1) > xp_to_next_level(0)
    assert xp_to_next_level(10) > xp_to_next_level(5)


def test_xp_curve_matches_phase_8_milestones():
    assert [xp_to_next_level(level) for level in range(5)] == [
        25.0,
        81.0,
        162.0,
        264.0,
        386.0,
    ]
    assert isinstance(xp_to_next_level(0), float)


def test_add_xp_below_threshold_does_not_level_up():
    character = Character(name="Test", level=0, xp=0)
    levels_gained = add_xp(character, 1)
    assert levels_gained == 0
    assert character.level == 0
    assert character.xp == 1


def test_add_xp_preserves_fractional_character_xp():
    character = Character(name="Test", level=0, xp=0.0)

    levels_gained = add_xp(character, 12.5)

    assert levels_gained == 0
    assert character.level == 0
    assert character.xp == 12.5


def test_add_xp_levels_up_and_carries_remainder():
    character = Character(name="Test", level=0, xp=0)
    needed = xp_to_next_level(0)
    levels_gained = add_xp(character, needed + 5)
    assert levels_gained == 1
    assert character.level == 1
    assert character.xp == 5


def test_add_xp_can_grant_multiple_levels_at_once():
    character = Character(name="Test", level=0, xp=0)
    huge_amount = xp_to_next_level(0) + xp_to_next_level(1) + 1
    levels_gained = add_xp(character, huge_amount)
    assert levels_gained == 2
    assert character.level == 2


def test_award_character_xp_logs_authoritative_gain(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Authoritative XP Award",
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

    levels_gained = award_character_xp(
        db_session,
        campaign.id,
        character,
        5,
        source=CharacterXPSource.SIGNIFICANT_CHALLENGE,
        experience_key="challenge:first-river-crossing",
    )

    assert levels_gained == 0
    assert character.level == 0
    assert character.xp == 5

    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign.id,
            WorldEvent.event_type
            == EventType.PLAYER_GAINED_XP.value,
            WorldEvent.actor_id
            == character.id,
        )
        .one()
    )

    payload = json.loads(
        event.payload_json
    )

    assert payload["amount"] == 5
    assert payload["source"] == CharacterXPSource.SIGNIFICANT_CHALLENGE.value
    assert payload["experience_key"] == "challenge:first-river-crossing"
    assert payload["current_xp"] == 5
    assert payload["current_level"] == 0


def test_award_character_xp_logs_each_level_crossed(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Multiple Level Events",
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

    amount = (
        xp_to_next_level(0)
        + xp_to_next_level(1)
        + 1
    )

    levels_gained = award_character_xp(
        db_session,
        campaign.id,
        character,
        amount,
        source=CharacterXPSource.DIFFICULT_SURVIVAL,
        experience_key="survival:collapsed-mine",
    )

    assert levels_gained == 2
    assert character.level == 2
    assert character.xp == 1

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign.id,
            WorldEvent.event_type
            == EventType.PLAYER_LEVELED_UP.value,
            WorldEvent.actor_id
            == character.id,
        )
        .all()
    )

    assert len(events) == 2

    transitions = {
        (
            json.loads(event.payload_json)[
                "previous_level"
            ],
            json.loads(event.payload_json)[
                "new_level"
            ],
        )
        for event in events
    }

    assert transitions == {
        (0, 1),
        (1, 2),
    }


def test_award_character_xp_rejects_wrong_campaign(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Correct Campaign",
    )

    other_campaign = create_campaign(
        db_session,
        "Wrong Campaign",
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

    with pytest.raises(
        ValueError,
        match="does not belong to campaign",
    ):
        award_character_xp(
            db_session,
            other_campaign.id,
            character,
            5,
            source=CharacterXPSource.RELEVANT_ACHIEVEMENT,
            experience_key="achievement:test",
        )

    assert character.level == 0
    assert character.xp == 0


def test_award_character_xp_does_not_reward_same_experience_twice(
    db_session,
):
    campaign = create_campaign(db_session, "Character XP Anti Farming")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    first_levels = award_character_xp(
        db_session,
        campaign.id,
        character,
        10,
        source=CharacterXPSource.IMPORTANT_DISCOVERY,
        experience_key="discovery:ancient-observatory",
    )
    repeated_levels = award_character_xp(
        db_session,
        campaign.id,
        character,
        10,
        source=CharacterXPSource.IMPORTANT_DISCOVERY,
        experience_key="discovery:ancient-observatory",
    )

    assert first_levels == 0
    assert repeated_levels == 0
    assert character.xp == 10
    assert (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type == EventType.PLAYER_GAINED_XP.value,
            WorldEvent.actor_id == character.id,
        )
        .count()
        == 1
    )


def test_award_character_xp_requires_backend_recognized_source(
    db_session,
):
    campaign = create_campaign(db_session, "Character XP Source")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    with pytest.raises(ValueError, match="Invalid Character XP source"):
        award_character_xp(
            db_session,
            campaign.id,
            character,
            5,
            source="ROUTINE_SKILL_CHECK",  # type: ignore[arg-type]
            experience_key="skill-check:repeatable",
        )

    assert character.xp == 0
