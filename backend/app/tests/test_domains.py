import pytest

from app.core.enums import DomainEvidenceSource
from app.db.models.domain import (
    CharacterDomainEvidence,
    CharacterDomainSynergy,
    DomainDefinition,
    DomainEvidenceRecord,
    DomainSynergyRecord,
)
from app.game.character.service import create_character
from app.game.domains.service import (
    award_domain_evidence,
    award_domain_synergy_evidence,
    domain_maturity,
)
from app.game.time.clock import advance_world_time
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session):
    for key, family in (
        ("SWORD", "WEAPON"),
        ("WIND", "MANIFESTATION"),
        ("MOBILITY", "COMBAT_STYLE"),
        ("TIME", "RARE_EXOTIC"),
    ):
        db_session.add(DomainDefinition(key=key, family=family, description=""))
    campaign = create_campaign(db_session, "Domain Test")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    return campaign, character


def test_catalog_presence_does_not_grant_domain_evidence(db_session):
    _campaign, character = _character(db_session)

    assert db_session.get(DomainDefinition, "TIME") is not None
    assert (
        db_session.query(CharacterDomainEvidence)
        .filter(CharacterDomainEvidence.character_id == character.id)
        .count()
        == 0
    )
    assert domain_maturity(db_session, character.id, "TIME").depth == 0


def test_authoritative_evidence_award_is_hidden_and_persistent(db_session):
    campaign, character = _character(db_session)

    award = award_domain_evidence(
        db_session,
        campaign.id,
        character,
        domain_key="SWORD",
        source=DomainEvidenceSource.TRAINING,
        evidence_key="training:guard-transitions",
        context_key="training-yard:first-session",
        amount=1.0,
    )

    assert award.evidence.depth == 1.0
    assert award.evidence.evidence_count == 1
    assert award.record.awarded_amount == 1.0


def test_unknown_domain_cannot_receive_evidence(db_session):
    campaign, character = _character(db_session)

    with pytest.raises(ValueError, match="Unknown domain"):
        award_domain_evidence(
            db_session,
            campaign.id,
            character,
            domain_key="INVENTED_POWER",
            source=DomainEvidenceSource.EXPERIENCE,
            evidence_key="invented",
            context_key="invented",
            amount=1.0,
        )


def test_identical_domain_training_has_recent_diminishing_returns(db_session):
    campaign, character = _character(db_session)
    common = {
        "domain_key": "SWORD",
        "source": DomainEvidenceSource.TRAINING,
        "evidence_key": "training:identical-tree-strike",
        "context_key": "same-tree",
        "amount": 1.0,
    }

    first = award_domain_evidence(db_session, campaign.id, character, **common)
    second = award_domain_evidence(db_session, campaign.id, character, **common)
    advance_world_time(db_session, campaign.id, 24 * 60 + 1)
    later = award_domain_evidence(db_session, campaign.id, character, **common)

    assert first.record.awarded_amount == 1.0
    assert second.record.awarded_amount == 0.5
    assert second.record.repetition_count == 1
    assert later.record.awarded_amount == 1.0
    maturity = domain_maturity(db_session, character.id, "SWORD")
    assert maturity.consistency == 1
    assert maturity.diversity == 1


def test_maturity_separates_depth_consistency_and_diversity(db_session):
    campaign, character = _character(db_session)
    for source, evidence_key, context_key in (
        (DomainEvidenceSource.TRAINING, "training:forms", "yard"),
        (DomainEvidenceSource.STUDY, "study:sword-manual", "library"),
        (DomainEvidenceSource.COMBAT, "combat:first-duel", "real-duel"),
    ):
        award_domain_evidence(
            db_session,
            campaign.id,
            character,
            domain_key="SWORD",
            source=source,
            evidence_key=evidence_key,
            context_key=context_key,
            amount=1.0,
        )

    maturity = domain_maturity(db_session, character.id, "SWORD")
    assert maturity.depth == 3.0
    assert maturity.consistency == 3
    assert maturity.diversity == 3
    assert maturity.synergy_depth == 0


def test_two_domains_do_not_create_synergy_automatically(db_session):
    campaign, character = _character(db_session)
    for domain in ("SWORD", "WIND"):
        award_domain_evidence(
            db_session,
            campaign.id,
            character,
            domain_key=domain,
            source=DomainEvidenceSource.TRAINING,
            evidence_key=f"training:{domain.lower()}",
            context_key="separate-training",
            amount=1.0,
        )

    assert db_session.query(CharacterDomainSynergy).count() == 0
    assert domain_maturity(db_session, character.id, "SWORD").synergy_depth == 0


def test_synergy_requires_and_records_real_integration(db_session):
    campaign, character = _character(db_session)
    with pytest.raises(ValueError, match="real evidence in both domains"):
        award_domain_synergy_evidence(
            db_session,
            campaign.id,
            character,
            first_domain_key="SWORD",
            second_domain_key="WIND",
            source=DomainEvidenceSource.EXPERIMENTATION,
            evidence_key="integration:wind-assisted-lunge",
            context_key="first-experiment",
            amount=1.0,
        )

    for domain in ("SWORD", "WIND"):
        award_domain_evidence(
            db_session,
            campaign.id,
            character,
            domain_key=domain,
            source=DomainEvidenceSource.TRAINING,
            evidence_key=f"training:{domain.lower()}",
            context_key="foundation",
            amount=1.0,
        )

    first = award_domain_synergy_evidence(
        db_session,
        campaign.id,
        character,
        first_domain_key="WIND",
        second_domain_key="SWORD",
        source=DomainEvidenceSource.EXPERIMENTATION,
        evidence_key="integration:wind-assisted-lunge",
        context_key="first-experiment",
        amount=1.0,
    )
    repeated = award_domain_synergy_evidence(
        db_session,
        campaign.id,
        character,
        first_domain_key="SWORD",
        second_domain_key="WIND",
        source=DomainEvidenceSource.EXPERIMENTATION,
        evidence_key="integration:wind-assisted-lunge",
        context_key="first-experiment",
        amount=1.0,
    )

    assert (first.synergy.first_domain_key, first.synergy.second_domain_key) == (
        "SWORD",
        "WIND",
    )
    assert first.record.awarded_amount == 1.0
    assert repeated.record.awarded_amount == 0.5
    maturity = domain_maturity(db_session, character.id, "SWORD")
    assert maturity.synergy_depth == 1.5
    assert maturity.synergy_count == 1


def test_domain_evidence_is_not_exposed_in_player_endpoints(
    client,
    db_session,
):
    campaign, character = _character(db_session)
    award_domain_evidence(
        db_session,
        campaign.id,
        character,
        domain_key="TIME",
        source=DomainEvidenceSource.EXPERIENCE,
        evidence_key="experience:temporal-anomaly",
        context_key="hidden-test",
        amount=1.0,
    )
    db_session.commit()

    sheet = client.get(
        f"/api/campaigns/{campaign.id}/character",
        params={"character_id": character.id},
    )
    journal = client.get(
        f"/api/campaigns/{campaign.id}/journal",
        params={"character_id": character.id},
    )

    assert sheet.status_code == 200
    assert "TIME" not in sheet.text
    assert journal.status_code == 200
    assert "DOMAIN" not in journal.text


def test_campaign_reset_removes_hidden_evidence_but_keeps_catalog(db_session):
    campaign, character = _character(db_session)
    award_domain_evidence(
        db_session,
        campaign.id,
        character,
        domain_key="SWORD",
        source=DomainEvidenceSource.TRAINING,
        evidence_key="training:forms",
        context_key="yard",
        amount=1.0,
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CharacterDomainEvidence).count() == 0
    assert db_session.query(DomainEvidenceRecord).count() == 0
    assert db_session.query(CharacterDomainSynergy).count() == 0
    assert db_session.query(DomainSynergyRecord).count() == 0
    assert db_session.get(DomainDefinition, "SWORD") is not None
