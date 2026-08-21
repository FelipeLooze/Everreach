import pytest

from app.core.enums import EventType, TechniqueLearningState, TechniqueOrigin, TechniqueType
from app.db.models.domain import DomainDefinition
from app.db.models.event import WorldEvent
from app.db.models.skill import CharacterTechnique
from app.game.character.service import create_character
from app.game.skills import techniques as technique_service
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Technique Learning")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    technique = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Passo do Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    db_session.flush()
    return campaign, character, technique


def _events(db_session, campaign_id, event_type):
    return (
        db_session.query(WorldEvent)
        .filter(WorldEvent.campaign_id == campaign_id, WorldEvent.event_type == event_type.value)
        .all()
    )


def test_absence_of_a_row_means_unknown(db_session):
    _campaign, character, technique = _setup(db_session)

    link = (
        db_session.query(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character.id,
            CharacterTechnique.technique_id == technique.id,
        )
        .one_or_none()
    )

    assert link is None
    assert technique not in technique_service.list_character_techniques(
        db_session, character.id
    )


def test_mark_technique_aware_records_state_and_origin(db_session):
    campaign, character, technique = _setup(db_session)

    link = technique_service.mark_technique_aware(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.OBSERVED
    )

    assert link.learning_state == TechniqueLearningState.AWARE.value
    assert link.origin == TechniqueOrigin.OBSERVED.value
    assert len(_events(db_session, campaign.id, EventType.TECHNIQUE_AWARENESS_GAINED)) == 1
    # Being merely aware does not make the technique usable.
    assert technique not in technique_service.list_character_techniques(db_session, character.id)


def test_mark_technique_aware_does_not_downgrade_further_progress(db_session):
    campaign, character, technique = _setup(db_session)
    technique_service.grant_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.SELF_DISCOVERED
    )

    link = technique_service.mark_technique_aware(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.OBSERVED
    )

    assert link.learning_state == TechniqueLearningState.LEARNED.value
    assert link.origin == TechniqueOrigin.SELF_DISCOVERED.value


def test_begin_learning_requires_prior_awareness(db_session):
    campaign, character, technique = _setup(db_session)

    with pytest.raises(technique_service.TechniqueLearningError, match="must be aware"):
        technique_service.begin_learning_technique(
            db_session, campaign.id, character, technique, origin=TechniqueOrigin.TAUGHT
        )


def test_begin_learning_transitions_aware_to_learning(db_session):
    campaign, character, technique = _setup(db_session)
    technique_service.mark_technique_aware(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.DOCUMENTED
    )

    link = technique_service.begin_learning_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.TAUGHT
    )

    assert link.learning_state == TechniqueLearningState.LEARNING.value
    assert link.origin == TechniqueOrigin.TAUGHT.value
    # Still not usable — knowing how to practice is not the same as knowing how to perform it.
    assert technique not in technique_service.list_character_techniques(db_session, character.id)


def test_grant_technique_works_directly_from_any_prior_state(db_session):
    campaign, character, technique = _setup(db_session)

    link = technique_service.grant_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.TAUGHT
    )

    assert link.learning_state == TechniqueLearningState.LEARNED.value
    assert technique in technique_service.list_character_techniques(db_session, character.id)


def test_resolve_technique_use_rejects_a_technique_that_is_only_aware_or_learning(
    db_session, monkeypatch
):
    campaign, character, technique = _setup(db_session)
    technique_service.mark_technique_aware(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.OBSERVED
    )

    with pytest.raises(technique_service.TechniqueUseError, match="has not learned"):
        technique_service.resolve_technique_use(
            db_session,
            campaign.id,
            character,
            technique_id=technique.id,
            action_key="attempt-while-aware",
        )

    technique_service.begin_learning_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.OBSERVED
    )

    with pytest.raises(technique_service.TechniqueUseError, match="has not learned"):
        technique_service.resolve_technique_use(
            db_session,
            campaign.id,
            character,
            technique_id=technique.id,
            action_key="attempt-while-learning",
        )
