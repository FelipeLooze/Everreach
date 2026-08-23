"""Phase 21C — Structured Visual Specification Foundation."""

from app.game.visual.spec import (
    get_visual_spec,
    resolve_visual_layers,
    set_current_visual_state,
    set_stable_visual_traits,
)
from app.game.world.seed import create_campaign


def test_get_visual_spec_is_empty_when_nothing_was_ever_established(db_session):
    campaign = create_campaign(db_session, "Visual Spec Vazio", world_seed=1)

    spec = get_visual_spec(db_session, "npc", "npc_inexistente", campaign_id=campaign.id)

    assert spec.stable == {}
    assert spec.current == {}


def test_set_stable_visual_traits_merges_rather_than_replaces(db_session):
    campaign = create_campaign(db_session, "Visual Spec Estavel Mescla", world_seed=2)

    set_stable_visual_traits(
        db_session, "npc", "npc_mira", {"hair_color": "red", "eye_color": "green"},
        campaign_id=campaign.id,
    )
    spec = set_stable_visual_traits(
        db_session, "npc", "npc_mira", {"permanent_scar": "left cheek"},
        campaign_id=campaign.id,
    )

    assert spec.stable == {
        "hair_color": "red", "eye_color": "green", "permanent_scar": "left cheek",
    }


def test_set_current_visual_state_merges_and_never_touches_stable(db_session):
    campaign = create_campaign(db_session, "Visual Spec Estado Atual", world_seed=3)
    set_stable_visual_traits(
        db_session, "npc", "npc_mira", {"hair_color": "red"}, campaign_id=campaign.id,
    )

    set_current_visual_state(
        db_session, "npc", "npc_mira", {"clothing": "work clothes"}, campaign_id=campaign.id,
    )
    spec = set_current_visual_state(
        db_session, "npc", "npc_mira", {"bandage": "forearm"}, campaign_id=campaign.id,
    )

    assert spec.current == {"clothing": "work clothes", "bandage": "forearm"}
    assert spec.stable == {"hair_color": "red"}


def test_stable_and_current_are_isolated_per_subject(db_session):
    campaign = create_campaign(db_session, "Visual Spec Isolado Por Sujeito", world_seed=4)
    set_stable_visual_traits(
        db_session, "npc", "npc_mira", {"hair_color": "red"}, campaign_id=campaign.id,
    )
    set_stable_visual_traits(
        db_session, "npc", "npc_logan", {"hair_color": "black"}, campaign_id=campaign.id,
    )

    mira = get_visual_spec(db_session, "npc", "npc_mira", campaign_id=campaign.id)
    logan = get_visual_spec(db_session, "npc", "npc_logan", campaign_id=campaign.id)

    assert mira.stable == {"hair_color": "red"}
    assert logan.stable == {"hair_color": "black"}


def test_isolated_per_subject_kind_even_with_the_same_id(db_session):
    campaign = create_campaign(db_session, "Visual Spec Isolado Por Tipo", world_seed=5)
    set_stable_visual_traits(
        db_session, "npc", "same_id", {"hair_color": "red"}, campaign_id=campaign.id,
    )
    set_stable_visual_traits(
        db_session, "creature", "same_id", {"species": "wolf"}, campaign_id=campaign.id,
    )

    npc_spec = get_visual_spec(db_session, "npc", "same_id", campaign_id=campaign.id)
    creature_spec = get_visual_spec(db_session, "creature", "same_id", campaign_id=campaign.id)

    assert npc_spec.stable == {"hair_color": "red"}
    assert creature_spec.stable == {"species": "wolf"}


def test_isolated_per_campaign(db_session):
    campaign_a = create_campaign(db_session, "Visual Spec Campanha A", world_seed=6)
    campaign_b = create_campaign(db_session, "Visual Spec Campanha B", world_seed=7)
    set_stable_visual_traits(
        db_session, "npc", "npc_mira", {"hair_color": "red"}, campaign_id=campaign_a.id,
    )

    spec_in_b = get_visual_spec(db_session, "npc", "npc_mira", campaign_id=campaign_b.id)

    assert spec_in_b.stable == {}


def test_campaign_global_subject_has_no_campaign_id(db_session):
    """ItemDefinition (Phase 10) is campaign-global — visual identity
    for it must be reachable without a campaign_id, and remain the
    same row across every campaign."""
    set_stable_visual_traits(
        db_session, "item_definition", "item_iron_sword", {"material": "iron"},
    )

    spec = get_visual_spec(db_session, "item_definition", "item_iron_sword")

    assert spec.stable == {"material": "iron"}


def test_resolve_visual_layers_lets_more_specific_layers_override():
    global_layer = {"clothing_material": "wool and linen", "tone": "modest"}
    regional_layer = {"clothing_material": "wool and linen"}
    personal_layer = {"clothing_material": "ceremonial silk"}

    result = resolve_visual_layers(global_layer, regional_layer, personal_layer)

    assert result["clothing_material"] == "ceremonial silk"
    assert result["tone"] == "modest"


def test_resolve_visual_layers_none_values_never_override_a_broader_default():
    broad = {"clothing_material": "wool and linen"}
    specific_with_no_opinion = {"clothing_material": None, "footwear": "boots"}

    result = resolve_visual_layers(broad, specific_with_no_opinion)

    assert result["clothing_material"] == "wool and linen"
    assert result["footwear"] == "boots"
