import json

import pytest

from app.core.enums import (
    EarthProfession,
    EventType,
    ProfessionActivityOutcome,
    ProfessionXPSource,
)
from app.db.models.event import WorldEvent
from app.game.character.service import create_character
from app.game.professions.activities import (
    award_crafting_xp,
    award_gathering_xp,
    award_practice_xp,
    award_work_xp,
)
from app.game.professions.service import award_profession_xp
from app.game.time.clock import advance_world_time
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session, *, earth_profession=None):
    campaign = create_campaign(db_session, "Profession Sources")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
        earth_profession=earth_profession,
    )
    return campaign, character


def test_first_common_herb_awards_point_one_herbalism_xp(db_session):
    campaign, character = _character(db_session)

    result = award_gathering_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        activity_key="gather:common-mint",
        task_complexity_level=0,
    )

    assert result.profession_xp_before_affinity == 0.1
    assert result.progress is not None
    assert result.progress.level == 0
    assert result.progress.xp == 0.1
    assert character.level == 0
    assert character.xp == 0


def test_repeating_identical_gathering_has_diminishing_returns(db_session):
    campaign, character = _character(db_session)

    first = award_gathering_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        activity_key="gather:common-mint",
        task_complexity_level=0,
    )
    second = award_gathering_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        activity_key="gather:common-mint",
        task_complexity_level=0,
    )
    novel = award_gathering_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        activity_key="gather:river-reed",
        task_complexity_level=0,
    )

    assert first.profession_xp_before_affinity == 0.1
    assert second.profession_xp_before_affinity == 0.05
    assert second.repetition_count == 1
    assert novel.profession_xp_before_affinity == 0.1
    assert novel.repetition_count == 0
    assert novel.progress is not None
    assert novel.progress.xp == pytest.approx(0.25)


def test_repetition_penalty_expires_after_one_world_day(db_session):
    campaign, character = _character(db_session)
    common = {
        "profession_key": "HERBALISM",
        "profession_name": "Herbalismo",
        "activity_key": "gather:common-mint",
        "task_complexity_level": 0,
    }
    award_gathering_xp(db_session, campaign.id, character, **common)
    immediate = award_gathering_xp(
        db_session,
        campaign.id,
        character,
        **common,
    )
    advance_world_time(db_session, campaign.id, 24 * 60 + 1)
    later = award_gathering_xp(
        db_session,
        campaign.id,
        character,
        **common,
    )

    assert immediate.repetition_multiplier == 0.5
    assert later.repetition_count == 0
    assert later.repetition_multiplier == 1.0


def test_work_crafting_and_practice_are_separate_sources(db_session):
    campaign, character = _character(db_session)
    common = {
        "profession_key": "CULINARY",
        "profession_name": "Culinária",
        "task_complexity_level": 0,
        "outcome": ProfessionActivityOutcome.SUCCESS,
    }

    work = award_work_xp(
        db_session,
        campaign.id,
        character,
        activity_key="work:kitchen-shift",
        base_xp=0.5,
        **common,
    )
    crafting = award_crafting_xp(
        db_session,
        campaign.id,
        character,
        activity_key="craft:vegetable-stew",
        base_xp=0.5,
        **common,
    )
    practice = award_practice_xp(
        db_session,
        campaign.id,
        character,
        activity_key="practice:knife-cuts",
        base_xp=0.5,
        **common,
    )

    assert [work.source, crafting.source, practice.source] == [
        ProfessionXPSource.WORK,
        ProfessionXPSource.CRAFTING,
        ProfessionXPSource.PRACTICE,
    ]
    assert practice.progress is not None
    assert practice.progress.xp == 1.5


def test_partial_outcome_and_learning_quality_reduce_award(db_session):
    campaign, character = _character(db_session)

    result = award_crafting_xp(
        db_session,
        campaign.id,
        character,
        profession_key="CARPENTRY",
        profession_name="Carpintaria",
        activity_key="craft:uneven-stool",
        base_xp=1.0,
        task_complexity_level=0,
        outcome=ProfessionActivityOutcome.PARTIAL,
        learning_quality=0.8,
    )

    assert result.profession_xp_before_affinity == pytest.approx(0.4)
    assert result.progress is not None
    assert result.progress.xp == pytest.approx(0.4)


def test_failure_is_recorded_without_creating_profession(db_session):
    campaign, character = _character(db_session)

    result = award_practice_xp(
        db_session,
        campaign.id,
        character,
        profession_key="BLACKSMITHING",
        profession_name="Ferraria",
        activity_key="practice:first-hammering",
        base_xp=0.5,
        task_complexity_level=0,
        outcome=ProfessionActivityOutcome.FAILURE,
    )

    assert result.profession_xp_before_affinity == 0
    assert result.progress is None
    activity = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.PLAYER_COMPLETED_PROFESSION_ACTIVITY.value
        )
        .one()
    )
    assert json.loads(activity.payload_json)["outcome"] == "FAILURE"


def test_trivial_task_loses_relevance_for_high_level_professional(db_session):
    campaign, character = _character(db_session)
    progress = award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        amount=100.0,
    )
    assert progress is not None
    assert progress.level == 10

    result = award_gathering_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        activity_key="gather:trivial-leaf",
        base_xp=1.0,
        task_complexity_level=0,
    )

    assert result.level_relevance_multiplier == pytest.approx(1 / 11)
    assert result.profession_xp_before_affinity == pytest.approx(1 / 11)


def test_background_affinity_applies_after_activity_factors(db_session):
    campaign, character = _character(
        db_session,
        earth_profession=EarthProfession.CHEF,
    )

    result = award_practice_xp(
        db_session,
        campaign.id,
        character,
        profession_key="CULINARY",
        profession_name="Culinária",
        activity_key="practice:first-stock",
        base_xp=0.5,
        task_complexity_level=0,
    )

    assert result.profession_xp_before_affinity == 0.5
    assert result.progress is not None
    assert result.progress.xp == pytest.approx(0.55)
