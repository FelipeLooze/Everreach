"""Phase 11I — Player-Created / Emergent Techniques.

A freeform attempt at a not-yet-recognized maneuver: the LLM only supplies
what the player described (via Intent.pattern_key/domains/technique_type);
the backend resolves everything mechanical (capability check, resource
cost, outcome) from authoritative facts. The result feeds technique-pattern
evidence (11C) — it never creates a Technique by itself.
"""

import pytest

from app.ai.llm_service import LLMService
from app.core.enums import ProfessionActivityOutcome
from app.db.models.domain import DomainDefinition
from app.db.models.technique_evidence import TechniqueExperimentRecord
from app.game.character.service import create_character
from app.game.progression.outcomes import resolve_progression_outcome
from app.game.skills import technique_evidence as evidence_service
from app.game.skills.technique_experimentation import (
    TECHNIQUE_EXPERIMENT_RESOURCE_COST,
    TechniqueExperimentError,
    resolve_technique_experiment,
)
from app.game.world.seed import create_campaign, seed_initial_region


class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "A ação acontece conforme o resultado mecânico."


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Technique Experiment")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    db_session.flush()
    return campaign, character


def test_an_unrecognizable_domain_is_a_noop(db_session):
    campaign, character = _setup(db_session)
    starting_mana = character.mana_current

    result = resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento algo bizarro sem sentido nenhum.",
        proposed_pattern_key=None,
        proposed_domains="NOT_A_REAL_DOMAIN",
        proposed_technique_type="MAGICAL",
        action_key="attempt-unknown",
    )

    assert "não corresponde" in result.mechanical_summary
    assert character.mana_current == starting_mana
    assert db_session.query(TechniqueExperimentRecord).count() == 0


def test_insufficient_resource_is_a_noop(db_session):
    campaign, character = _setup(db_session)
    character.mana_current = 1  # below TECHNIQUE_EXPERIMENT_RESOURCE_COST

    result = resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento comprimir vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="attempt-no-mana",
    )

    assert "não tem mana" in result.mechanical_summary
    assert character.mana_current == 1
    assert db_session.query(TechniqueExperimentRecord).count() == 0


def test_a_magical_experiment_spends_mana(db_session):
    campaign, character = _setup(db_session)
    starting_mana = character.mana_current

    resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento comprimir vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="attempt-1",
        rng=SequenceRng(10),
    )

    assert character.mana_current == starting_mana - TECHNIQUE_EXPERIMENT_RESOURCE_COST


def test_a_physical_experiment_spends_stamina_not_mana(db_session):
    campaign, character = _setup(db_session)
    if db_session.get(DomainDefinition, "SWORD") is None:
        db_session.add(DomainDefinition(key="SWORD", family="WEAPON", description=""))
        db_session.flush()
    starting_mana = character.mana_current
    starting_stamina = character.stamina_current

    resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento um golpe giratório com a espada.",
        proposed_pattern_key="spinning-strike",
        proposed_domains="SWORD",
        proposed_technique_type="PHYSICAL",
        action_key="attempt-physical",
        rng=SequenceRng(10),
    )

    assert character.mana_current == starting_mana
    assert character.stamina_current == starting_stamina - TECHNIQUE_EXPERIMENT_RESOURCE_COST


def test_replaying_the_same_action_key_does_not_roll_or_spend_again(db_session):
    campaign, character = _setup(db_session)

    first = resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento comprimir vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="attempt-replay",
        rng=SequenceRng(10),
    )
    mana_after_first = character.mana_current

    second = resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento comprimir vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="attempt-replay",
        rng=SequenceRng(1),  # would be a different roll if it re-rolled
    )

    assert second.replayed is True
    assert second.mechanical_summary == first.mechanical_summary
    assert character.mana_current == mana_after_first
    assert db_session.query(TechniqueExperimentRecord).count() == 1


@pytest.mark.parametrize(
    "roll,expected_outcome",
    [
        (20, ProfessionActivityOutcome.SUCCESS),   # critical
        (17, ProfessionActivityOutcome.SUCCESS),   # total 17, margin 5
        (14, ProfessionActivityOutcome.PARTIAL),   # total 14, margin 2
        (5, ProfessionActivityOutcome.FAILURE),    # total 5 < dc 12
    ],
)
def test_outcome_classification_by_roll_margin(db_session, roll, expected_outcome):
    campaign, character = _setup(db_session)

    result = resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento comprimir vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key=f"attempt-roll-{roll}",
        rng=SequenceRng(roll),
    )

    record = db_session.query(TechniqueExperimentRecord).filter_by(
        action_key=f"attempt-roll-{roll}"
    ).one()
    assert record.outcome == expected_outcome.value


def test_pattern_key_falls_back_to_a_slug_of_the_raw_text_in_portuguese(db_session):
    campaign, character = _setup(db_session)

    resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu comprimo vento na palma da mão!",
        proposed_pattern_key=None,
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="attempt-fallback-slug",
        rng=SequenceRng(10),
    )

    record = db_session.query(TechniqueExperimentRecord).one()
    assert record.pattern_key == "eu-comprimo-vento-na-palma-da-mao"


def test_successful_experiment_feeds_technique_pattern_evidence(db_session):
    campaign, character = _setup(db_session)

    result = resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento comprimir vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="attempt-evidence",
        rng=SequenceRng(20),  # guaranteed critical success
    )
    resolve_progression_outcome(
        db_session, PassiveLLM(), campaign.id, character, result.progression_outcome
    )

    maturity = evidence_service.technique_pattern_maturity(
        db_session, character.id, "wind-palm-compress"
    )
    assert maturity.depth > 0
    assert maturity.evidence_count == 1


def test_a_failed_attempt_still_produces_a_small_amount_of_evidence(db_session):
    campaign, character = _setup(db_session)

    result = resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento comprimir vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="attempt-failure",
        rng=SequenceRng(2),  # guaranteed failure (total 2 < dc 12, not a nat 1)
    )
    resolve_progression_outcome(
        db_session, PassiveLLM(), campaign.id, character, result.progression_outcome
    )

    maturity = evidence_service.technique_pattern_maturity(
        db_session, character.id, "wind-palm-compress"
    )
    assert 0 < maturity.depth < TECHNIQUE_EXPERIMENT_RESOURCE_COST  # much smaller than a success


def test_repeating_the_identical_pattern_has_diminishing_evidence_returns(db_session):
    campaign, character = _setup(db_session)

    first = resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento comprimir vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="attempt-a",
        rng=SequenceRng(20),
    )
    second = resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu tento comprimir vento na palma da mão de novo.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="attempt-b",
        rng=SequenceRng(20),
    )
    resolve_progression_outcome(db_session, PassiveLLM(), campaign.id, character, first.progression_outcome)
    resolve_progression_outcome(db_session, PassiveLLM(), campaign.id, character, second.progression_outcome)

    maturity = evidence_service.technique_pattern_maturity(
        db_session, character.id, "wind-palm-compress"
    )
    # Second award used repetition_multiplier 0.5, so total depth is 1.5x one
    # award, not 2x.
    assert maturity.evidence_count == 2
    assert maturity.depth == pytest.approx(1.5 * 1.0)  # TECHNIQUE_EXPERIMENT_BASE_EVIDENCE


def test_character_from_a_different_campaign_is_rejected(db_session):
    campaign, character = _setup(db_session)
    other_campaign = create_campaign(db_session, "Other Campaign")

    with pytest.raises(TechniqueExperimentError, match="does not belong"):
        resolve_technique_experiment(
            db_session, other_campaign.id, character,
            raw_text="Eu tento algo.",
            proposed_pattern_key="something",
            proposed_domains="WIND",
            proposed_technique_type="MAGICAL",
            action_key="attempt-wrong-campaign",
        )
