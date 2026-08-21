import pytest

from app.core.enums import (
    DomainEvidenceSource,
    EventType,
    ProfessionActivityOutcome,
    TechniqueLearningState,
    TechniqueType,
)
from app.db.models.domain import DomainDefinition
from app.db.models.event import WorldEvent
from app.db.models.skill import CharacterTechnique
from app.game.character.service import create_character
from app.game.skills import technique_evidence as evidence_service
from app.game.skills import techniques as technique_service
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Technique Recognition")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    db_session.flush()
    return campaign, character


def _mature_pattern(db_session, campaign, character, pattern_key="wind-step"):
    for index in range(4):
        evidence_service.award_technique_pattern_evidence(
            db_session,
            campaign.id,
            character,
            pattern_key=pattern_key,
            domain_keys=("WIND",),
            technique_type=TechniqueType.MAGICAL,
            source=DomainEvidenceSource.EXPERIMENTATION,
            outcome=ProfessionActivityOutcome.SUCCESS,
            evidence_key=f"attempt-{index}",
            context_key="location:test",
            base_amount=2.0,
        )


def test_recognizing_an_immature_pattern_is_rejected(db_session):
    campaign, character = _setup(db_session)
    evidence_service.award_technique_pattern_evidence(
        db_session,
        campaign.id,
        character,
        pattern_key="wind-step",
        domain_keys=("WIND",),
        technique_type=TechniqueType.MAGICAL,
        source=DomainEvidenceSource.EXPERIMENTATION,
        outcome=ProfessionActivityOutcome.SUCCESS,
        evidence_key="only-attempt",
        context_key="location:test",
        base_amount=1.0,
    )

    with pytest.raises(technique_service.TechniqueRecognitionError, match="not yet reproducible"):
        technique_service.recognize_technique_from_pattern(
            db_session,
            campaign.id,
            character,
            pattern_key="wind-step",
            name="Passo do Vento",
        )


def test_recognizing_a_mature_pattern_persists_and_grants_the_technique(db_session):
    campaign, character = _setup(db_session)
    _mature_pattern(db_session, campaign, character)

    technique = technique_service.recognize_technique_from_pattern(
        db_session,
        campaign.id,
        character,
        pattern_key="wind-step",
        name="Passo do Vento",
        description="Um impulso rápido guiado por uma corrente de vento controlada.",
    )

    assert technique.name == "Passo do Vento"
    assert technique.technique_type == TechniqueType.MAGICAL.value
    assert [row.domain_key for row in technique.domains] == ["WIND"]

    link = (
        db_session.query(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character.id,
            CharacterTechnique.technique_id == technique.id,
        )
        .one()
    )
    assert link.learning_state == TechniqueLearningState.LEARNED.value
    assert link.origin == "SELF_DISCOVERED"
    assert technique in technique_service.list_character_techniques(db_session, character.id)


def test_recognition_emits_a_distinct_event_from_ordinary_learning(db_session):
    campaign, character = _setup(db_session)
    _mature_pattern(db_session, campaign, character)

    technique_service.recognize_technique_from_pattern(
        db_session,
        campaign.id,
        character,
        pattern_key="wind-step",
        name="Passo do Vento",
    )

    recognized_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type == EventType.TECHNIQUE_RECOGNIZED.value,
        )
        .all()
    )
    learned_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type == EventType.TECHNIQUE_LEARNED.value,
        )
        .all()
    )
    assert len(recognized_events) == 1
    assert len(learned_events) == 1


def test_a_freshly_recognized_technique_can_be_used(db_session, monkeypatch):
    campaign, character = _setup(db_session)
    _mature_pattern(db_session, campaign, character)
    technique = technique_service.recognize_technique_from_pattern(
        db_session,
        campaign.id,
        character,
        pattern_key="wind-step",
        name="Passo do Vento",
    )

    from app.game import dice
    from app.game.combat.service import SkillCheckResult

    monkeypatch.setattr(
        technique_service,
        "resolve_skill_check",
        lambda *_args, **_kwargs: SkillCheckResult(
            skill_name="Wind",
            dc=12,
            roll=dice.RollResult(sides=20, raw=20, modifier=0),
            success=True,
            critical=True,
        ),
    )

    use = technique_service.resolve_technique_use(
        db_session,
        campaign.id,
        character,
        technique_id=technique.id,
        action_key="use-recognized-technique",
    )

    assert use.record.success is True
