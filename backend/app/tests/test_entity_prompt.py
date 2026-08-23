"""Phase 23D-N — entity-kind dispatch for automatic prompt derivation."""
import pytest

from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item, list_inventory
from app.game.visual.entity_prompt import (
    UnsupportedGenerationTargetError,
    resolve_generation_inputs,
)
from app.game.visual.npc import NPCVisualIdentityError, set_npc_stable_identity
from app.db.models.npc import NPC
from app.game.world.seed import create_campaign, seed_initial_region


def _npc(db_session, campaign_id, region_id, location_id, name="Mira"):
    npc = NPC(campaign_id=campaign_id, region_id=region_id, location_id=location_id, name=name, role="ferreira")
    db_session.add(npc)
    db_session.flush()
    return npc


def test_resolve_generation_inputs_for_npc_portrait(db_session):
    campaign = create_campaign(db_session, "Entity Prompt NPC", world_seed=1001)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "silver"})
    db_session.commit()

    workflow_key, workflow_version, prompt_text, seed = resolve_generation_inputs(
        db_session, campaign.id, "npc", npc.id, "NPC_PORTRAIT"
    )

    assert workflow_key == "EVERREACH_NPC_PORTRAIT"
    assert workflow_version == "V1"
    assert "silver" in prompt_text
    assert isinstance(seed, int)


def test_resolve_generation_inputs_raises_for_unknown_npc(db_session):
    campaign = create_campaign(db_session, "Entity Prompt NPC Missing", world_seed=1002)

    with pytest.raises(NPCVisualIdentityError):
        resolve_generation_inputs(db_session, campaign.id, "npc", "npc_does_not_exist", "NPC_PORTRAIT")


def test_resolve_generation_inputs_for_item_illustration(db_session):
    campaign = create_campaign(db_session, "Entity Prompt Item", world_seed=1003)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    get_or_create_item(db_session, "Machado de Ferro", item_type="weapon")
    add_item(db_session, character.id, "Machado de Ferro")
    db_session.commit()
    instance = list_inventory(db_session, character.id)[0]

    workflow_key, workflow_version, prompt_text, seed = resolve_generation_inputs(
        db_session, campaign.id, "item_instance", instance.id, "ITEM_ILLUSTRATION"
    )

    assert workflow_key == "EVERREACH_ITEM"
    assert workflow_version == "V3"
    assert prompt_text
    assert isinstance(seed, int)


def test_resolve_generation_inputs_rejects_an_unsupported_combination(db_session):
    campaign = create_campaign(db_session, "Entity Prompt Unsupported", world_seed=1004)

    with pytest.raises(UnsupportedGenerationTargetError):
        resolve_generation_inputs(db_session, campaign.id, "location", "loc_x", "LOCATION_SCENE")
