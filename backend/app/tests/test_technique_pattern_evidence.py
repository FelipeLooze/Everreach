import pytest

from app.ai.llm_service import LLMService
from app.core.enums import DomainEvidenceSource, ProfessionActivityOutcome, TechniqueType
from app.db.models.domain import DomainDefinition
from app.db.models.progression_outcome import AppliedProgressionOutcome
from app.game.character.service import create_character
from app.game.progression.outcomes import (
    ProgressionOutcome,
    TechniquePatternProgressGain,
    resolve_progression_outcome,
)
from app.game.skills import technique_evidence as evidence_service
from app.game.world.seed import create_campaign, seed_initial_region


class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "A ação acontece conforme o resultado mecânico."


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Technique Pattern Evidence")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    db_session.flush()
    return campaign, character


def _award(db_session, campaign, character, *, outcome=ProfessionActivityOutcome.SUCCESS, evidence_key="drill", amount=1.0):
    return evidence_service.award_technique_pattern_evidence(
        db_session,
        campaign.id,
        character,
        pattern_key="wind-step",
        domain_keys=("WIND",),
        technique_type=TechniqueType.MAGICAL,
        source=DomainEvidenceSource.EXPERIMENTATION,
        outcome=outcome,
        evidence_key=evidence_key,
        context_key="location:test",
        base_amount=amount,
    )


def test_unattempted_pattern_has_no_maturity(db_session):
    _campaign, character = _setup(db_session)

    maturity = evidence_service.technique_pattern_maturity(db_session, character.id, "wind-step")

    assert maturity.depth == 0.0
    assert maturity.evidence_count == 0
    assert maturity.mature is False
    assert maturity.domain_keys == ()


def test_first_attempt_records_evidence_but_is_not_mature(db_session):
    campaign, character = _setup(db_session)

    award = _award(db_session, campaign, character)

    assert award.evidence.evidence_count == 1
    assert award.evidence.depth == pytest.approx(1.0)
    maturity = evidence_service.technique_pattern_maturity(db_session, character.id, "wind-step")
    assert maturity.mature is False


def test_repeating_the_same_evidence_key_has_diminishing_returns(db_session):
    campaign, character = _setup(db_session)

    first = _award(db_session, campaign, character, evidence_key="drill")
    second = _award(db_session, campaign, character, evidence_key="drill")
    third = _award(db_session, campaign, character, evidence_key="drill")

    assert first.repetition_multiplier == pytest.approx(1.0)
    assert second.repetition_multiplier == pytest.approx(0.5)
    assert third.repetition_multiplier == pytest.approx(1 / 3)


def test_varying_evidence_key_avoids_the_same_repetition_counter(db_session):
    campaign, character = _setup(db_session)

    first = _award(db_session, campaign, character, evidence_key="drill")
    varied = _award(db_session, campaign, character, evidence_key="real-attempt")

    assert first.repetition_multiplier == pytest.approx(1.0)
    assert varied.repetition_multiplier == pytest.approx(1.0)


def test_outcome_quality_scales_the_awarded_amount(db_session):
    campaign, character = _setup(db_session)

    success = _award(db_session, campaign, character, outcome=ProfessionActivityOutcome.SUCCESS, evidence_key="a")
    partial = _award(db_session, campaign, character, outcome=ProfessionActivityOutcome.PARTIAL, evidence_key="b")
    failure = _award(db_session, campaign, character, outcome=ProfessionActivityOutcome.FAILURE, evidence_key="c")

    assert success.record.awarded_amount == pytest.approx(1.0)
    assert partial.record.awarded_amount == pytest.approx(0.5)
    assert failure.record.awarded_amount == pytest.approx(0.25)


def test_pattern_becomes_mature_after_enough_reproducible_success(db_session):
    campaign, character = _setup(db_session)

    for i in range(4):
        _award(db_session, campaign, character, evidence_key=f"attempt-{i}", amount=2.0)

    maturity = evidence_service.technique_pattern_maturity(db_session, character.id, "wind-step")
    assert maturity.evidence_count == 4
    assert maturity.depth == pytest.approx(8.0)
    assert maturity.mature is True
    assert maturity.domain_keys == ("WIND",)
    assert maturity.technique_type == TechniqueType.MAGICAL.value


def test_rejects_inconsistent_domains_for_the_same_pattern(db_session):
    campaign, character = _setup(db_session)
    if db_session.get(DomainDefinition, "SWORD") is None:
        db_session.add(DomainDefinition(key="SWORD", family="WEAPON", description=""))
        db_session.flush()
    _award(db_session, campaign, character)

    with pytest.raises(evidence_service.TechniquePatternEvidenceError, match="different domains"):
        evidence_service.award_technique_pattern_evidence(
            db_session,
            campaign.id,
            character,
            pattern_key="wind-step",
            domain_keys=("WIND", "SWORD"),
            technique_type=TechniqueType.MAGICAL,
            source=DomainEvidenceSource.EXPERIMENTATION,
            outcome=ProfessionActivityOutcome.SUCCESS,
            evidence_key="different-domains",
            context_key="location:test",
            base_amount=1.0,
        )


def test_rejects_inconsistent_type_for_the_same_pattern(db_session):
    campaign, character = _setup(db_session)
    _award(db_session, campaign, character)

    with pytest.raises(evidence_service.TechniquePatternEvidenceError, match="different type"):
        evidence_service.award_technique_pattern_evidence(
            db_session,
            campaign.id,
            character,
            pattern_key="wind-step",
            domain_keys=("WIND",),
            technique_type=TechniqueType.PHYSICAL,
            source=DomainEvidenceSource.EXPERIMENTATION,
            outcome=ProfessionActivityOutcome.SUCCESS,
            evidence_key="different-type",
            context_key="location:test",
            base_amount=1.0,
        )


def test_rejects_an_unknown_domain(db_session):
    _campaign, character = _setup(db_session)
    campaign = _campaign

    with pytest.raises(evidence_service.TechniquePatternEvidenceError, match="unknown domain"):
        evidence_service.award_technique_pattern_evidence(
            db_session,
            campaign.id,
            character,
            pattern_key="wind-step",
            domain_keys=("NOT_A_REAL_DOMAIN",),
            technique_type=TechniqueType.MAGICAL,
            source=DomainEvidenceSource.EXPERIMENTATION,
            outcome=ProfessionActivityOutcome.SUCCESS,
            evidence_key="a",
            context_key="location:test",
            base_amount=1.0,
        )


def test_resolve_progression_outcome_applies_pattern_evidence_exactly_once(db_session):
    campaign, character = _setup(db_session)
    outcome = ProgressionOutcome(
        outcome_key="wind-step-attempt-001",
        technique_patterns=(
            TechniquePatternProgressGain(
                pattern_key="wind-step",
                domain_keys=("WIND",),
                technique_type=TechniqueType.MAGICAL,
                source=DomainEvidenceSource.EXPERIMENTATION,
                outcome=ProfessionActivityOutcome.SUCCESS,
                evidence_key="attempt-001",
                context_key="location:test",
                base_amount=1.0,
            ),
        ),
    )

    resolve_progression_outcome(db_session, PassiveLLM(), campaign.id, character, outcome)
    resolve_progression_outcome(db_session, PassiveLLM(), campaign.id, character, outcome)

    maturity = evidence_service.technique_pattern_maturity(db_session, character.id, "wind-step")
    assert maturity.evidence_count == 1
    assert db_session.query(AppliedProgressionOutcome).count() == 1
