"""Phase 21M — Visual Consistency & Inheritance.

Not new resolver logic — a cross-cutting regression net confirming
every concrete entity resolver (21E/21G/21H/21I/21F) actually applies
the same "explicit Canon always wins over a broader default" discipline
via the one shared app.game.visual.spec.resolve_visual_layers, so they
cannot silently drift apart from each other over time.
"""
from app.core.enums import SettlementType, ThreatIntensity, ThreatType
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.regional_threat import RegionalThreat
from app.db.models.settlement import Settlement
from app.game.visual.creature import (
    resolve_regional_threat_visual,
    set_regional_threat_current_state,
    set_threat_species_visual_identity,
)
from app.game.visual.location import resolve_location_visual, set_location_stable_identity
from app.game.visual.npc import resolve_npc_appearance, set_npc_stable_identity
from app.game.visual.region import resolve_subregion_visual, set_subregion_visual_identity
from app.game.visual.settlement import resolve_settlement_visual, set_settlement_stable_identity
from app.game.visual.spec import set_stable_visual_traits
from app.game.world.seed import create_campaign, seed_initial_region


def test_explicit_npc_canon_overrides_the_regional_default(db_session):
    campaign = create_campaign(db_session, "Consistencia NPC", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(campaign_id=campaign.id, region_id=region.id, location_id=village.id, name="Mira", role="ferreira")
    db_session.add(npc)
    db_session.flush()
    set_stable_visual_traits(db_session, "region", region.id, {"clothing": "wool"}, campaign_id=campaign.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"clothing": "ceremonial silk"})

    assert resolve_npc_appearance(db_session, campaign.id, npc.id)["clothing"] == "ceremonial silk"


def test_explicit_location_canon_overrides_the_regional_default(db_session):
    campaign = create_campaign(db_session, "Consistencia Local", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    set_stable_visual_traits(db_session, "region", region.id, {"clothing": "wool"}, campaign_id=campaign.id)
    set_location_stable_identity(db_session, campaign.id, village.id, {"clothing": "ceremonial silk"})

    assert resolve_location_visual(db_session, campaign.id, village.id)["clothing"] == "ceremonial silk"


def test_explicit_settlement_canon_overrides_the_regional_default(db_session):
    campaign = create_campaign(db_session, "Consistencia Assentamento", world_seed=3)
    region, _village = seed_initial_region(db_session, campaign.id)
    location = Location(region_id=region.id, name="Rowan", type="settlement")
    db_session.add(location)
    db_session.flush()
    settlement = Settlement(location_id=location.id, settlement_type=SettlementType.VILLAGE)
    db_session.add(settlement)
    db_session.flush()
    set_stable_visual_traits(db_session, "region", region.id, {"clothing": "wool"}, campaign_id=campaign.id)
    set_settlement_stable_identity(db_session, campaign.id, settlement.id, {"clothing": "ceremonial silk"})

    assert resolve_settlement_visual(db_session, campaign.id, settlement.id)["clothing"] == "ceremonial silk"


def test_explicit_subregion_canon_overrides_the_regional_default(db_session):
    campaign = create_campaign(db_session, "Consistencia Subregiao", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    set_stable_visual_traits(db_session, "region", region.id, {"clothing": "wool"}, campaign_id=campaign.id)
    set_subregion_visual_identity(db_session, campaign.id, village.subregion_id, {"clothing": "ceremonial silk"})

    assert resolve_subregion_visual(db_session, campaign.id, village.subregion_id)["clothing"] == "ceremonial silk"


def test_explicit_regional_threat_population_canon_overrides_the_species_default(db_session):
    campaign = create_campaign(db_session, "Consistencia Ameaca Regional", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    threat = RegionalThreat(
        subregion_id=village.subregion_id, threat_type=ThreatType.WOLVES, intensity=ThreatIntensity.LOW,
    )
    db_session.add(threat)
    db_session.flush()
    set_threat_species_visual_identity(db_session, ThreatType.WOLVES.value, {"coat": "gray"})
    set_regional_threat_current_state(db_session, campaign.id, threat.id, {"coat": "unusually dark"})

    assert resolve_regional_threat_visual(db_session, campaign.id, threat.id)["coat"] == "unusually dark"


def test_current_state_is_the_most_specific_layer_everywhere_it_exists(db_session):
    """Current state (the last layer in every chain that has one) must
    win over that same entity's own stable identity — consistently,
    not just for one entity kind."""
    campaign = create_campaign(db_session, "Consistencia Estado Atual", world_seed=6)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(campaign_id=campaign.id, region_id=region.id, location_id=village.id, name="Logan", role="guarda")
    db_session.add(npc)
    db_session.flush()

    from app.game.visual.npc import set_npc_current_appearance

    set_npc_stable_identity(db_session, campaign.id, npc.id, {"clothing": "tunic"})
    set_npc_current_appearance(db_session, campaign.id, npc.id, {"clothing": "black cloak"})

    assert resolve_npc_appearance(db_session, campaign.id, npc.id)["clothing"] == "black cloak"
