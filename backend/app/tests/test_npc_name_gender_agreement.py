"""Regression test for a real bug report: the 3 starting NPCs (Phase 15)
each have a fixed-gender role ("ancião da vila"/"estalajadeiro" masculine,
"ferreira" feminine) but their given name was drawn from one ungendered
pool with plain random.choice — a name that reads as feminine ("Astra")
could land on the masculine "ancião da vila" role, and the narrator, with
no gender field to check, described the NPC as "um homem" from the role
noun alone while addressing them by their (feminine-reading) name.

generate_npc_name's `gender` parameter now picks a matching given-name
pool per role; this asserts that agreement holds across many generated
campaigns, not just the one seed that happened to be reported.
"""

from app.db.models.npc import NPC
from app.game.world.content_pools import NPC_GIVEN_NAME_POOL_FEM, NPC_GIVEN_NAME_POOL_MASC
from app.game.world.seed import create_campaign, seed_initial_region


def _given_name(npc: NPC) -> str:
    return npc.name.split(" ", 1)[0]


def test_starting_npc_given_names_agree_with_their_roles_fixed_gender(db_session):
    for seed in range(30):
        campaign = create_campaign(db_session, f"Campanha {seed}", world_seed=seed)
        _region, village = seed_initial_region(db_session, campaign.id)

        npcs_by_role = {
            npc.role: npc
            for npc in db_session.query(NPC).filter(
                NPC.campaign_id == campaign.id, NPC.location_id == village.id
            )
        }

        elder = npcs_by_role["ancião da vila"]
        blacksmith = npcs_by_role["ferreira"]
        innkeeper = npcs_by_role["estalajadeiro"]

        assert _given_name(elder) in NPC_GIVEN_NAME_POOL_MASC
        assert _given_name(blacksmith) in NPC_GIVEN_NAME_POOL_FEM
        assert _given_name(innkeeper) in NPC_GIVEN_NAME_POOL_MASC
