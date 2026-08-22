"""Regression test for a real bug: generated NPC names (Phase 15 follow-up
— elder/blacksmith/innkeeper/org-leader names) must never collide with the
3 fixed SimulatedPlayer names (Corren Ashvale, Dessa Marrow, Bram Holt —
Phase 7) placed at the same starting village. app.game.engine._handle_talk
resolves TALK targets by substring match across BOTH NPCs and
SimulatedPlayers at the same location — a name collision makes that
resolution genuinely ambiguous ("Há mais de uma pessoa correspondente"),
which is exactly what caused
test_apply_intent_talk_completes_matching_quest_objective to flake.
"""

from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game.world.seed import create_campaign, seed_initial_region

FIXED_SIMULATED_PLAYER_NAMES = {"Corren Ashvale", "Dessa Marrow", "Bram Holt"}


def test_no_generated_npc_name_ever_collides_with_a_simulated_player_name(db_session):
    for seed in range(30):
        campaign = create_campaign(db_session, f"Campanha {seed}", world_seed=seed)
        region, _village = seed_initial_region(db_session, campaign.id)

        npc_names = {
            npc.name for npc in db_session.query(NPC).filter(NPC.campaign_id == campaign.id).all()
        }
        simulated_player_names = {
            player.name
            for player in db_session.query(SimulatedPlayer).filter(SimulatedPlayer.campaign_id == campaign.id).all()
        }

        assert simulated_player_names == FIXED_SIMULATED_PLAYER_NAMES
        assert npc_names.isdisjoint(simulated_player_names)
