"""Regression test for a real bug report: every procedurally-generated
NPC (the 3 starting NPCs, plus every settlement/organization leader)
had NO stable visual identity at all — resolve_npc_appearance() always
returned an empty dict for them, and build_npc_portrait_prompt() raises
VisualPromptBuilderError on an empty appearance, so NPC portrait
generation (Phase 23D) could never succeed for a single real NPC in
actual gameplay, only for hand-built test fixtures that set traits
explicitly. seed_initial_region now gives every NPC it creates a
baseline stable identity via set_npc_stable_identity.
"""

from app.db.models.npc import NPC
from app.game.visual.entity_prompt import resolve_generation_inputs
from app.game.visual.npc import resolve_npc_appearance
from app.game.world.seed import create_campaign, seed_initial_region


def test_every_generated_npc_has_a_non_empty_resolved_appearance(db_session):
    campaign = create_campaign(db_session, "Visual Identity Test")
    _region, _village = seed_initial_region(db_session, campaign.id)

    npcs = db_session.query(NPC).filter(NPC.campaign_id == campaign.id).all()
    assert len(npcs) >= 4  # elder + blacksmith + innkeeper + at least 1 org leader

    for npc in npcs:
        appearance = resolve_npc_appearance(db_session, campaign.id, npc.id)
        assert appearance, f"{npc.name} ({npc.role}) resolved to an empty appearance"


def test_generated_npc_portrait_prompt_resolves_without_error(db_session):
    campaign = create_campaign(db_session, "Visual Identity Prompt Test")
    _region, village = seed_initial_region(db_session, campaign.id)

    elder = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.role == "ancião da vila").one()

    workflow_key, _version, prompt_text, _seed, reference_image = resolve_generation_inputs(
        db_session, campaign.id, "npc", elder.id, "NPC_PORTRAIT"
    )

    assert workflow_key == "EVERREACH_NPC_PORTRAIT"
    assert reference_image is None
    assert "hair" in prompt_text
    assert "eyes" in prompt_text
