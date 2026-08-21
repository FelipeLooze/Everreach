"""Phase 11J — LLM Proposal + Backend Validation.

The LLM only ever gives a mature pattern a name/description; the backend
validates the proposal against the SAME authoritative evidence it gathered
— never accepts a number, an unevidenced element, or a status-effect claim
the LLM invents.
"""

import pytest

from app.ai.llm_service import LLMService, LLMServiceError
from app.db.models.domain import DomainDefinition
from app.game.character.service import create_character
from app.game.progression.outcomes import resolve_progression_outcome
from app.game.skills.technique_experimentation import resolve_technique_experiment
from app.game.skills.technique_naming import (
    TechniqueIdentityProposal,
    TechniqueNamingError,
    _validate_identity_proposal,
    gather_technique_pattern_evidence_summary,
    propose_and_recognize_technique,
)
from app.game.skills import techniques as technique_service
from app.game.time import clock
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


class FixedLLM(LLMService):
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.responses[len(self.calls) - 1]


class UnavailableLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        raise LLMServiceError("offline")


class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "A ação acontece conforme o resultado mecânico."


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Technique Naming")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    db_session.commit()
    return campaign, character


def _mature_pattern(db_session, campaign, character, pattern_key="wind-palm-compress", attempts=5):
    # Resource economy isn't what's under test here — keep mana from being
    # the bottleneck to reaching maturity.
    character.mana_current = 1000.0
    passive_llm = PassiveLLM()
    for index in range(attempts):
        result = resolve_technique_experiment(
            db_session, campaign.id, character,
            raw_text="Eu comprimo vento na palma da mão.",
            proposed_pattern_key=pattern_key,
            proposed_domains="WIND",
            proposed_technique_type="MAGICAL",
            action_key=f"mature-attempt-{index}",
            rng=SequenceRng(20),
        )
        resolve_progression_outcome(
            db_session, passive_llm, campaign.id, character, result.progression_outcome
        )
        # Past the 24h anti-farm window (11C), so each attempt counts fully —
        # matches the intended "practiced across real time," not spam.
        clock.advance_world_time(db_session, campaign.id, 25 * 60)
    db_session.commit()


def test_gathering_evidence_for_an_immature_pattern_is_rejected(db_session):
    campaign, character = _setup(db_session)
    resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu comprimo vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="only-attempt",
    )

    with pytest.raises(TechniqueNamingError, match="not mature"):
        gather_technique_pattern_evidence_summary(db_session, character.id, "wind-palm-compress")


def test_gathering_evidence_summarizes_domains_resource_and_outcomes(db_session):
    campaign, character = _setup(db_session)
    _mature_pattern(db_session, campaign, character)

    summary = gather_technique_pattern_evidence_summary(
        db_session, character.id, "wind-palm-compress"
    )

    assert summary.domain_keys == ("WIND",)
    assert summary.technique_type == "MAGICAL"
    assert summary.resource_key == "MANA"
    assert summary.success_count == 5
    assert summary.partial_count == 0
    assert summary.failure_count == 0


def test_validation_rejects_a_numeric_mechanical_claim():
    from app.game.skills.technique_naming import TechniquePatternEvidenceSummary

    summary = TechniquePatternEvidenceSummary(
        pattern_key="wind-palm-compress", domain_keys=("WIND",), technique_type="MAGICAL",
        depth=5.0, evidence_count=5, resource_key="MANA", average_resource_cost=3.0,
        success_count=5, partial_count=0, failure_count=0,
    )
    proposal = TechniqueIdentityProposal(
        name="Rajada de Vento",
        description="Causa 40 de dano e custa 12 de mana.",
    )

    violations = _validate_identity_proposal(proposal, summary)

    assert any("numérico" in v for v in violations)


def test_validation_rejects_an_unevidenced_status_effect():
    from app.game.skills.technique_naming import TechniquePatternEvidenceSummary

    summary = TechniquePatternEvidenceSummary(
        pattern_key="wind-palm-compress", domain_keys=("WIND",), technique_type="MAGICAL",
        depth=5.0, evidence_count=5, resource_key="MANA", average_resource_cost=3.0,
        success_count=5, partial_count=0, failure_count=0,
    )
    proposal = TechniqueIdentityProposal(
        name="Rajada Atordoante",
        description="Um golpe de vento que sempre atordoa o alvo.",
    )

    violations = _validate_identity_proposal(proposal, summary)

    assert any("efeito de status" in v for v in violations)


def test_validation_rejects_an_unevidenced_element():
    from app.game.skills.technique_naming import TechniquePatternEvidenceSummary

    summary = TechniquePatternEvidenceSummary(
        pattern_key="wind-palm-compress", domain_keys=("WIND",), technique_type="MAGICAL",
        depth=5.0, evidence_count=5, resource_key="MANA", average_resource_cost=3.0,
        success_count=5, partial_count=0, failure_count=0,
    )
    proposal = TechniqueIdentityProposal(
        name="Explosão de Fogo Congelante",
        description="Uma rajada que queima e congela tudo ao redor.",
    )

    violations = _validate_identity_proposal(proposal, summary)

    assert any("FIRE" in v for v in violations)
    assert any("COLD" in v or "ICE" in v for v in violations)


def test_validation_accepts_a_clean_proposal():
    from app.game.skills.technique_naming import TechniquePatternEvidenceSummary

    summary = TechniquePatternEvidenceSummary(
        pattern_key="wind-palm-compress", domain_keys=("WIND",), technique_type="MAGICAL",
        depth=5.0, evidence_count=5, resource_key="MANA", average_resource_cost=3.0,
        success_count=5, partial_count=0, failure_count=0,
    )
    proposal = TechniqueIdentityProposal(
        name="Rajada Comprimida",
        description="Uma liberação concentrada de vento comprimido, produzindo um impulso direcional curto.",
    )

    assert _validate_identity_proposal(proposal, summary) == []


def test_a_clean_proposal_recognizes_the_technique_on_the_first_attempt(db_session):
    campaign, character = _setup(db_session)
    _mature_pattern(db_session, campaign, character)
    llm = FixedLLM(
        '{"name": "Rajada Comprimida", "description": "Uma liberação concentrada '
        'de vento comprimido, produzindo um impulso direcional curto."}'
    )

    technique = propose_and_recognize_technique(
        db_session, campaign.id, character, llm, pattern_key="wind-palm-compress"
    )

    assert technique is not None
    assert technique.name == "Rajada Comprimida"
    assert len(llm.calls) == 1
    assert technique in technique_service.list_character_techniques(db_session, character.id)


def test_a_bad_proposal_gets_one_retry_and_then_succeeds(db_session):
    campaign, character = _setup(db_session)
    _mature_pattern(db_session, campaign, character)
    llm = FixedLLM(
        '{"name": "Explosão de Fogo", "description": "Causa 40 de dano de fogo."}',
        '{"name": "Rajada Comprimida", "description": "Uma liberação concentrada '
        'de vento comprimido, produzindo um impulso direcional curto."}',
    )

    technique = propose_and_recognize_technique(
        db_session, campaign.id, character, llm, pattern_key="wind-palm-compress"
    )

    assert technique is not None
    assert technique.name == "Rajada Comprimida"
    assert len(llm.calls) == 2
    # The retry prompt should explain what to fix.
    assert "violou" in llm.calls[1][1]


def test_two_bad_proposals_in_a_row_leave_the_pattern_unrecognized(db_session):
    campaign, character = _setup(db_session)
    _mature_pattern(db_session, campaign, character)
    llm = FixedLLM(
        '{"name": "Explosão de Fogo", "description": "Causa 40 de dano de fogo."}',
        '{"name": "Gelo Atordoante", "description": "Sempre atordoa com frio congelante."}',
    )

    technique = propose_and_recognize_technique(
        db_session, campaign.id, character, llm, pattern_key="wind-palm-compress"
    )

    assert technique is None
    assert len(llm.calls) == 2
    assert technique_service.list_character_techniques(db_session, character.id) == []


def test_an_unavailable_llm_returns_none_without_crashing(db_session):
    campaign, character = _setup(db_session)
    _mature_pattern(db_session, campaign, character)

    technique = propose_and_recognize_technique(
        db_session, campaign.id, character, UnavailableLLM(), pattern_key="wind-palm-compress"
    )

    assert technique is None


def test_a_malformed_response_is_treated_as_no_proposal(db_session):
    campaign, character = _setup(db_session)
    _mature_pattern(db_session, campaign, character)
    llm = FixedLLM("isso não é JSON", "também não é JSON")

    technique = propose_and_recognize_technique(
        db_session, campaign.id, character, llm, pattern_key="wind-palm-compress"
    )

    assert technique is None


def test_naming_an_immature_pattern_raises_without_calling_the_llm(db_session):
    campaign, character = _setup(db_session)
    resolve_technique_experiment(
        db_session, campaign.id, character,
        raw_text="Eu comprimo vento na palma da mão.",
        proposed_pattern_key="wind-palm-compress",
        proposed_domains="WIND",
        proposed_technique_type="MAGICAL",
        action_key="only-attempt",
    )
    llm = FixedLLM('{"name": "x", "description": "y"}')

    with pytest.raises(TechniqueNamingError):
        propose_and_recognize_technique(
            db_session, campaign.id, character, llm, pattern_key="wind-palm-compress"
        )

    assert len(llm.calls) == 0
