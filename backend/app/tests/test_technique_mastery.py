import pytest

from app.core.enums import TechniqueMasteryTier, TechniqueOrigin, TechniqueType
from app.db.models.domain import DomainDefinition
from app.db.models.skill import CharacterTechnique
from app.game import dice
from app.game.character.service import create_character
from app.game.combat.service import SkillCheckResult
from app.game.skills import technique_mastery as mastery_service
from app.game.skills import techniques as technique_service
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Technique Mastery")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    technique = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Passo do Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    technique_service.grant_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.SELF_DISCOVERED
    )
    db_session.flush()
    return campaign, character, technique


@pytest.mark.parametrize(
    "mastery,expected_tier",
    [
        (0.0, TechniqueMasteryTier.UNSTABLE),
        (0.99, TechniqueMasteryTier.UNSTABLE),
        (1.0, TechniqueMasteryTier.BASIC),
        (5.99, TechniqueMasteryTier.BASIC),
        (6.0, TechniqueMasteryTier.PRACTICED),
        (14.99, TechniqueMasteryTier.PRACTICED),
        (15.0, TechniqueMasteryTier.REFINED),
        (29.99, TechniqueMasteryTier.REFINED),
        (30.0, TechniqueMasteryTier.MASTERED),
        (1000.0, TechniqueMasteryTier.MASTERED),
    ],
)
def test_mastery_tier_thresholds(mastery, expected_tier):
    assert mastery_service.technique_mastery_tier(mastery) == expected_tier


def test_reliability_bonus_increases_monotonically_with_tier():
    bonuses = [
        mastery_service.technique_mastery_reliability_bonus(value)
        for value in (0.0, 1.0, 6.0, 15.0, 30.0)
    ]
    assert bonuses == sorted(bonuses)
    assert bonuses[0] == 0
    assert bonuses[-1] > 0


def test_award_technique_mastery_requires_an_existing_relationship(db_session):
    _campaign, character, technique = _setup(db_session)
    other_technique = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada Solta",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )

    with pytest.raises(ValueError, match="does not have a relationship"):
        mastery_service.award_technique_mastery(
            db_session, character.id, other_technique.id, amount=1.0
        )


def test_award_technique_mastery_rejects_non_positive_amounts(db_session):
    _campaign, character, technique = _setup(db_session)

    with pytest.raises(ValueError, match="must be positive"):
        mastery_service.award_technique_mastery(db_session, character.id, technique.id, amount=0)


def test_award_technique_mastery_grows_the_stored_value(db_session):
    _campaign, character, technique = _setup(db_session)

    mastery_service.award_technique_mastery(db_session, character.id, technique.id, amount=2.0)
    mastery_service.award_technique_mastery(db_session, character.id, technique.id, amount=1.5)

    link = (
        db_session.query(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character.id,
            CharacterTechnique.technique_id == technique.id,
        )
        .one()
    )
    assert link.mastery == pytest.approx(3.5)


def test_character_technique_mastery_tier_reads_the_current_tier(db_session):
    _campaign, character, technique = _setup(db_session)
    assert (
        mastery_service.character_technique_mastery_tier(db_session, character.id, technique.id)
        == TechniqueMasteryTier.UNSTABLE
    )

    mastery_service.award_technique_mastery(db_session, character.id, technique.id, amount=10.0)

    assert (
        mastery_service.character_technique_mastery_tier(db_session, character.id, technique.id)
        == TechniqueMasteryTier.PRACTICED
    )


def _use(db_session, campaign, character, technique, *, action_key, roll_raw):
    return technique_service.resolve_technique_use(
        db_session,
        campaign.id,
        character,
        technique_id=technique.id,
        action_key=action_key,
    ), roll_raw


def test_successful_use_grows_mastery_more_than_a_failed_use(db_session, monkeypatch):
    campaign, character, technique = _setup(db_session)

    def fake_check(*_args, **_kwargs):
        return SkillCheckResult(
            skill_name="Manipulação do Vento",
            dc=12,
            roll=dice.RollResult(sides=20, raw=15, modifier=0),
            success=True,
            critical=False,
        )

    monkeypatch.setattr(technique_service, "resolve_skill_check", fake_check)
    use = technique_service.resolve_technique_use(
        db_session,
        campaign.id,
        character,
        technique_id=technique.id,
        action_key="success-use",
    )
    success_gain = next(iter(use.progression_outcome.technique_masteries)).amount

    def fake_failed_check(*_args, **_kwargs):
        return SkillCheckResult(
            skill_name="Manipulação do Vento",
            dc=12,
            roll=dice.RollResult(sides=20, raw=2, modifier=0),
            success=False,
            critical=False,
        )

    monkeypatch.setattr(technique_service, "resolve_skill_check", fake_failed_check)
    failed_use = technique_service.resolve_technique_use(
        db_session,
        campaign.id,
        character,
        technique_id=technique.id,
        action_key="failed-use",
    )
    failure_gain = next(iter(failed_use.progression_outcome.technique_masteries)).amount

    assert success_gain > failure_gain > 0


def test_critical_success_grows_mastery_more_than_plain_success(db_session, monkeypatch):
    campaign, character, technique = _setup(db_session)

    monkeypatch.setattr(
        technique_service,
        "resolve_skill_check",
        lambda *_a, **_k: SkillCheckResult(
            skill_name="x", dc=12,
            roll=dice.RollResult(sides=20, raw=20, modifier=0),
            success=True, critical=True,
        ),
    )
    critical_use = technique_service.resolve_technique_use(
        db_session, campaign.id, character, technique_id=technique.id, action_key="crit-use"
    )
    critical_gain = next(iter(critical_use.progression_outcome.technique_masteries)).amount

    assert critical_gain == pytest.approx(
        technique_service.TECHNIQUE_MASTERY_GAIN
        * technique_service.TECHNIQUE_MASTERY_CRITICAL_MULTIPLIER
    )


def test_accumulated_mastery_raises_the_execution_reliability_bonus(db_session, monkeypatch):
    campaign, character, technique = _setup(db_session)
    mastery_service.award_technique_mastery(db_session, character.id, technique.id, amount=30.0)

    captured = {}

    def capturing_check(*_args, bonus_modifier=0, **_kwargs):
        captured["bonus_modifier"] = bonus_modifier
        return SkillCheckResult(
            skill_name="x", dc=12,
            roll=dice.RollResult(sides=20, raw=10, modifier=bonus_modifier),
            success=True, critical=False,
        )

    monkeypatch.setattr(technique_service, "resolve_skill_check", capturing_check)
    technique_service.resolve_technique_use(
        db_session, campaign.id, character, technique_id=technique.id, action_key="mastered-use"
    )

    assert captured["bonus_modifier"] == mastery_service.technique_mastery_reliability_bonus(30.0)
    assert captured["bonus_modifier"] > 0
