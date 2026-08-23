"""Phase 21F — Creature Visual Identity."""

import pytest

from app.core.enums import ThreatIntensity, ThreatType
from app.db.models.regional_threat import RegionalThreat
from app.game.visual.creature import (
    CreatureVisualIdentityError,
    resolve_regional_threat_visual,
    set_regional_threat_current_state,
    set_threat_species_visual_identity,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _threat(db_session, subregion_id, threat_type=ThreatType.WOLVES):
    threat = RegionalThreat(subregion_id=subregion_id, threat_type=threat_type, intensity=ThreatIntensity.LOW)
    db_session.add(threat)
    db_session.flush()
    return threat


def test_species_identity_is_shared_across_every_population_of_that_species(db_session):
    campaign_a = create_campaign(db_session, "Especie Compartilhada A", world_seed=1)
    campaign_b = create_campaign(db_session, "Especie Compartilhada B", world_seed=2)
    region_a, village_a = seed_initial_region(db_session, campaign_a.id)
    region_b, village_b = seed_initial_region(db_session, campaign_b.id)
    threat_a = _threat(db_session, village_a.subregion_id or region_a.id)
    threat_b = _threat(db_session, village_b.subregion_id or region_b.id)
    set_threat_species_visual_identity(db_session, ThreatType.WOLVES.value, {"coat": "gray"})

    resolved_a = resolve_regional_threat_visual(db_session, campaign_a.id, threat_a.id)
    resolved_b = resolve_regional_threat_visual(db_session, campaign_b.id, threat_b.id)

    assert resolved_a["coat"] == "gray"
    assert resolved_b["coat"] == "gray"


def test_a_specific_population_can_override_the_shared_species_default(db_session):
    campaign = create_campaign(db_session, "Populacao Sobrescreve Especie", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    threat = _threat(db_session, village.subregion_id or region.id)
    set_threat_species_visual_identity(db_session, ThreatType.WOLVES.value, {"coat": "gray", "size": "normal"})
    set_regional_threat_current_state(db_session, campaign.id, threat.id, {"size": "unusually large"})

    resolved = resolve_regional_threat_visual(db_session, campaign.id, threat.id)

    assert resolved["size"] == "unusually large"
    assert resolved["coat"] == "gray"


def test_different_species_are_visually_independent(db_session):
    campaign = create_campaign(db_session, "Especies Independentes", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    wolves = _threat(db_session, village.subregion_id or region.id, ThreatType.WOLVES)
    boars = _threat(db_session, village.subregion_id or region.id, ThreatType.BOARS)
    set_threat_species_visual_identity(db_session, ThreatType.WOLVES.value, {"coat": "gray"})
    set_threat_species_visual_identity(db_session, ThreatType.BOARS.value, {"coat": "brown, bristled"})

    assert resolve_regional_threat_visual(db_session, campaign.id, wolves.id)["coat"] == "gray"
    assert resolve_regional_threat_visual(db_session, campaign.id, boars.id)["coat"] == "brown, bristled"


def test_population_with_no_species_identity_established_resolves_empty(db_session):
    campaign = create_campaign(db_session, "Sem Identidade De Especie", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    threat = _threat(db_session, village.subregion_id or region.id)

    resolved = resolve_regional_threat_visual(db_session, campaign.id, threat.id)

    assert resolved == {}


def test_raises_for_a_nonexistent_regional_threat(db_session):
    campaign = create_campaign(db_session, "Ameaca Regional Inexistente", world_seed=6)

    with pytest.raises(CreatureVisualIdentityError):
        resolve_regional_threat_visual(db_session, campaign.id, "threat_nao_existe")
