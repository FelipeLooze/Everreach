"""Phase 17Q — Exploration Progression Integration."""

from app.core.enums import DiscoverySignificance, DomainEvidenceSource, ExpeditionStatus
from app.db.models.domain import CharacterDomainEvidence, DomainDefinition
from app.db.models.expedition import Expedition
from app.game.character.service import create_character
from app.game.exploration.progression import (
    ExplorationProgressionSignal,
    apply_exploration_progression_signal,
    signal_for_cartography,
    signal_for_expedition,
    signal_for_successful_exploration,
)
from app.game.exploration.service import ExplorationOutcome
from app.game.world.seed import create_campaign


def test_a_failed_exploration_produces_no_signal():
    outcome = ExplorationOutcome(success=False, minutes_spent=90)
    assert signal_for_successful_exploration(outcome) is None


def test_a_minor_discovery_produces_a_small_experience_signal():
    outcome = ExplorationOutcome(
        success=True, minutes_spent=90, found_connection_id="conn_1", found_location_id="loc_1",
        significance=DiscoverySignificance.MINOR,
    )
    signal = signal_for_successful_exploration(outcome)
    assert signal.domain_key == "SURVEY"
    assert signal.source == DomainEvidenceSource.EXPERIENCE
    assert signal.amount == 1.0


def test_a_major_discovery_produces_a_larger_achievement_signal():
    outcome = ExplorationOutcome(
        success=True, minutes_spent=90, found_connection_id="conn_1", found_location_id="loc_1",
        significance=DiscoverySignificance.MAJOR,
    )
    signal = signal_for_successful_exploration(outcome)
    assert signal.source == DomainEvidenceSource.ACHIEVEMENT
    assert signal.amount == 5.0


def test_expedition_signals_only_exist_for_successful_or_partial_outcomes(db_session):
    campaign = create_campaign(db_session, "Sinal De Expedicao", world_seed=1)
    expedition = Expedition(
        campaign_id=campaign.id, group_id="group_fake", purpose="", origin_location_id="loc_fake",
        status=ExpeditionStatus.FAILED.value,
    )
    assert signal_for_expedition(expedition) is None

    expedition.status = ExpeditionStatus.SUCCEEDED.value
    signal = signal_for_expedition(expedition)
    assert signal.amount == 5.0
    assert signal.domain_key == "EXPEDITION"

    expedition.status = ExpeditionStatus.PARTIAL_SUCCESS.value
    signal = signal_for_expedition(expedition)
    assert signal.amount == 2.0


def test_cartography_signal_always_targets_the_cartography_domain():
    from app.db.models.map import Map

    map_row = Map(
        item_instance_id="item_fake", subject_kind="settlement", entity_id="loc_fake",
        creator_type="PLAYER", creator_id="char_fake", created_world_minute=0, content_json="{}",
    )
    signal = signal_for_cartography(map_row)
    assert signal.domain_key == "CARTOGRAPHY"
    assert signal.source == DomainEvidenceSource.EXPERIENCE


def test_applying_a_signal_for_an_unknown_domain_is_a_safe_no_op(db_session):
    campaign = create_campaign(db_session, "Dominio Desconhecido", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")

    signal = ExplorationProgressionSignal(
        domain_key="SURVEY", source=DomainEvidenceSource.EXPERIENCE,
        evidence_key="location_discovered", context_key="loc_1", amount=1.0,
    )

    result = apply_exploration_progression_signal(db_session, campaign.id, logan, signal)
    assert result is None


def test_applying_a_signal_for_a_real_domain_awards_evidence(db_session):
    campaign = create_campaign(db_session, "Dominio Real", world_seed=3)
    logan = create_character(db_session, campaign.id, "Logan")
    db_session.add(DomainDefinition(key="SURVEY", family="EXPLORATION", description=""))
    db_session.flush()

    signal = ExplorationProgressionSignal(
        domain_key="SURVEY", source=DomainEvidenceSource.EXPERIENCE,
        evidence_key="location_discovered", context_key="loc_1", amount=1.0,
    )

    result = apply_exploration_progression_signal(db_session, campaign.id, logan, signal)
    assert result is not None

    evidence = (
        db_session.query(CharacterDomainEvidence)
        .filter(CharacterDomainEvidence.character_id == logan.id, CharacterDomainEvidence.domain_key == "SURVEY")
        .one()
    )
    assert evidence.depth > 0
