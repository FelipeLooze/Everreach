import pytest

from app.db.models.domain import DomainDefinition
from app.game.character.service import create_character
from app.game.domains.service import award_domain_evidence, resolve_domain_check
from app.core.enums import DomainEvidenceSource
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Domain Check")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    db_session.flush()
    return campaign, character


def test_rejects_an_empty_domain_list(db_session):
    _campaign, character = _setup(db_session)

    with pytest.raises(ValueError, match="At least one domain"):
        resolve_domain_check(db_session, character.id, ())


def test_zero_depth_still_resolves_a_check(db_session):
    _campaign, character = _setup(db_session)

    result = resolve_domain_check(
        db_session, character.id, ("WIND",), dc=12, rng=SequenceRng(15)
    )

    assert result.roll.modifier == 0
    assert result.roll.total == 15
    assert result.success is True


def test_accumulated_depth_raises_the_modifier(db_session):
    campaign, character = _setup(db_session)
    award_domain_evidence(
        db_session, campaign.id, character,
        domain_key="WIND", source=DomainEvidenceSource.TRAINING,
        evidence_key="a", context_key="location:test", amount=12.0,
    )

    result = resolve_domain_check(
        db_session, character.id, ("WIND",), dc=12, rng=SequenceRng(10)
    )

    assert result.roll.modifier == 2  # 12.0 // 5
    assert result.roll.total == 12
    assert result.success is True


def test_natural_1_always_fails_regardless_of_modifier(db_session):
    campaign, character = _setup(db_session)
    award_domain_evidence(
        db_session, campaign.id, character,
        domain_key="WIND", source=DomainEvidenceSource.TRAINING,
        evidence_key="a", context_key="location:test", amount=100.0,
    )

    result = resolve_domain_check(
        db_session, character.id, ("WIND",), dc=12, rng=SequenceRng(1)
    )

    assert result.success is False


def test_natural_20_is_always_a_critical_success(db_session):
    _campaign, character = _setup(db_session)

    result = resolve_domain_check(
        db_session, character.id, ("WIND",), dc=999, rng=SequenceRng(20)
    )

    assert result.critical is True
    assert result.success is True


def test_multiple_domains_use_the_average_depth(db_session):
    campaign, character = _setup(db_session)
    if db_session.get(DomainDefinition, "SWORD") is None:
        db_session.add(DomainDefinition(key="SWORD", family="WEAPON", description=""))
        db_session.flush()
    award_domain_evidence(
        db_session, campaign.id, character,
        domain_key="WIND", source=DomainEvidenceSource.TRAINING,
        evidence_key="a", context_key="location:test", amount=20.0,
    )
    # SWORD stays at depth 0.0 -> average is 10.0 -> modifier 10.0 // 5 = 2

    result = resolve_domain_check(
        db_session, character.id, ("WIND", "SWORD"), dc=12, rng=SequenceRng(10)
    )

    assert result.roll.modifier == 2
