"""Phase 11G — Hybrid Techniques.

Audit found a real gap: technique_pattern_maturity (11C) only ever checked
the PATTERN's own reproducibility (repeated attempts at this exact
maneuver) — it never consulted Phase 8's Domain Synergy at all. That meant
a multi-domain pattern could become "mature" (and therefore recognizable
as a real Technique) purely from repetition, even if the character never
once genuinely combined the domains — exactly what the spec calls out as
forbidden: "Possessing two domains is NOT enough."

Fix: a pattern spanning 2+ domains now also requires real Domain Synergy
(depth > 0) between every pair it draws on. Domain Synergy itself can only
exist once the character has real evidence in BOTH domains AND has used
them together (Phase 8's own award_domain_synergy_evidence already
enforces this) — so this reuses Phase 8's authority rather than
duplicating it.
"""

import pytest

from app.core.enums import DomainEvidenceSource, ProfessionActivityOutcome, TechniqueType
from app.db.models.domain import DomainDefinition
from app.game.character.service import create_character
from app.game.domains.service import award_domain_evidence, award_domain_synergy_evidence
from app.game.skills import technique_evidence as evidence_service
from app.game.skills import techniques as technique_service
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session, *domain_keys):
    for key in domain_keys:
        if db_session.get(DomainDefinition, key) is None:
            db_session.add(DomainDefinition(key=key, family="TEST", description=""))
    campaign = create_campaign(db_session, "Hybrid Technique Synergy")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    db_session.flush()
    return campaign, character


def _mature_pattern_evidence(db_session, campaign, character, *, pattern_key, domain_keys):
    for index in range(4):
        evidence_service.award_technique_pattern_evidence(
            db_session,
            campaign.id,
            character,
            pattern_key=pattern_key,
            domain_keys=domain_keys,
            technique_type=TechniqueType.HYBRID,
            source=DomainEvidenceSource.EXPERIMENTATION,
            outcome=ProfessionActivityOutcome.SUCCESS,
            evidence_key=f"attempt-{index}",
            context_key="location:test",
            base_amount=2.0,
        )


def test_reproducibility_alone_is_not_enough_for_a_two_domain_pattern(db_session):
    campaign, character = _setup(db_session, "WIND", "SWORD")
    _mature_pattern_evidence(
        db_session, campaign, character,
        pattern_key="wind-blade", domain_keys=("WIND", "SWORD"),
    )

    maturity = evidence_service.technique_pattern_maturity(db_session, character.id, "wind-blade")

    assert maturity.reproducible is True
    assert maturity.has_required_synergy is False
    assert maturity.mature is False


def test_possessing_both_domains_separately_is_still_not_enough(db_session):
    campaign, character = _setup(db_session, "WIND", "SWORD")
    _mature_pattern_evidence(
        db_session, campaign, character,
        pattern_key="wind-blade", domain_keys=("WIND", "SWORD"),
    )
    # Develop each domain on its own — never combined.
    award_domain_evidence(
        db_session, campaign.id, character,
        domain_key="WIND", source=DomainEvidenceSource.TRAINING,
        evidence_key="solo-wind", context_key="location:test", amount=5.0,
    )
    award_domain_evidence(
        db_session, campaign.id, character,
        domain_key="SWORD", source=DomainEvidenceSource.TRAINING,
        evidence_key="solo-sword", context_key="location:test", amount=5.0,
    )

    maturity = evidence_service.technique_pattern_maturity(db_session, character.id, "wind-blade")

    assert maturity.has_required_synergy is False
    assert maturity.mature is False


def test_real_domain_synergy_unlocks_maturity(db_session):
    campaign, character = _setup(db_session, "WIND", "SWORD")
    _mature_pattern_evidence(
        db_session, campaign, character,
        pattern_key="wind-blade", domain_keys=("WIND", "SWORD"),
    )
    award_domain_evidence(
        db_session, campaign.id, character,
        domain_key="WIND", source=DomainEvidenceSource.TRAINING,
        evidence_key="a", context_key="location:test", amount=5.0,
    )
    award_domain_evidence(
        db_session, campaign.id, character,
        domain_key="SWORD", source=DomainEvidenceSource.TRAINING,
        evidence_key="b", context_key="location:test", amount=5.0,
    )
    award_domain_synergy_evidence(
        db_session, campaign.id, character,
        first_domain_key="WIND", second_domain_key="SWORD",
        source=DomainEvidenceSource.EXPERIMENTATION,
        evidence_key="integrated-attempt", context_key="location:test", amount=1.0,
    )

    maturity = evidence_service.technique_pattern_maturity(db_session, character.id, "wind-blade")

    assert maturity.has_required_synergy is True
    assert maturity.mature is True


def test_single_domain_patterns_are_unaffected_by_the_synergy_requirement(db_session):
    campaign, character = _setup(db_session, "WIND")
    _mature_pattern_evidence(
        db_session, campaign, character,
        pattern_key="wind-push", domain_keys=("WIND",),
    )

    maturity = evidence_service.technique_pattern_maturity(db_session, character.id, "wind-push")

    assert maturity.has_required_synergy is True
    assert maturity.mature is True


def test_a_three_domain_pattern_requires_synergy_for_every_pair(db_session):
    campaign, character = _setup(db_session, "WIND", "SWORD", "FIRE")
    _mature_pattern_evidence(
        db_session, campaign, character,
        pattern_key="triple-fusion", domain_keys=("WIND", "SWORD", "FIRE"),
    )
    for key in ("WIND", "SWORD", "FIRE"):
        award_domain_evidence(
            db_session, campaign.id, character,
            domain_key=key, source=DomainEvidenceSource.TRAINING,
            evidence_key=f"solo-{key}", context_key="location:test", amount=5.0,
        )
    # Only WIND<->SWORD synergy exists; FIRE was never integrated with either.
    award_domain_synergy_evidence(
        db_session, campaign.id, character,
        first_domain_key="WIND", second_domain_key="SWORD",
        source=DomainEvidenceSource.EXPERIMENTATION,
        evidence_key="wind-sword", context_key="location:test", amount=1.0,
    )

    maturity = evidence_service.technique_pattern_maturity(db_session, character.id, "triple-fusion")

    assert maturity.has_required_synergy is False
    assert maturity.mature is False


def test_recognition_gives_a_distinct_error_for_missing_synergy(db_session):
    campaign, character = _setup(db_session, "WIND", "SWORD")
    _mature_pattern_evidence(
        db_session, campaign, character,
        pattern_key="wind-blade", domain_keys=("WIND", "SWORD"),
    )

    with pytest.raises(
        technique_service.TechniqueRecognitionError, match="not been genuinely integrated"
    ):
        technique_service.recognize_technique_from_pattern(
            db_session, campaign.id, character,
            pattern_key="wind-blade", name="Lâmina do Vento",
        )


def test_recognition_succeeds_once_synergy_is_real(db_session):
    campaign, character = _setup(db_session, "WIND", "SWORD")
    _mature_pattern_evidence(
        db_session, campaign, character,
        pattern_key="wind-blade", domain_keys=("WIND", "SWORD"),
    )
    award_domain_evidence(
        db_session, campaign.id, character,
        domain_key="WIND", source=DomainEvidenceSource.TRAINING,
        evidence_key="a", context_key="location:test", amount=5.0,
    )
    award_domain_evidence(
        db_session, campaign.id, character,
        domain_key="SWORD", source=DomainEvidenceSource.TRAINING,
        evidence_key="b", context_key="location:test", amount=5.0,
    )
    award_domain_synergy_evidence(
        db_session, campaign.id, character,
        first_domain_key="WIND", second_domain_key="SWORD",
        source=DomainEvidenceSource.EXPERIMENTATION,
        evidence_key="integrated-attempt", context_key="location:test", amount=1.0,
    )

    technique = technique_service.recognize_technique_from_pattern(
        db_session, campaign.id, character,
        pattern_key="wind-blade", name="Lâmina do Vento",
    )

    assert technique.name == "Lâmina do Vento"
    assert technique in technique_service.list_character_techniques(db_session, character.id)
