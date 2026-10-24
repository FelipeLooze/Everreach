"""Starting village, part 1: every NPC has a structured personality, and
toward transported people nobody goes past distrustful (2026-10-24)."""

import json
import random

from app.ai import people_present
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.npcs import profile
from app.game.world.seed import create_campaign, seed_initial_region


def _village_npcs(db_session):
    campaign = create_campaign(db_session, "Perfis")
    region, village = seed_initial_region(db_session, campaign.id)
    create_character(db_session, campaign.id, "Logan", region.id, village.id)
    return db_session.query(NPC).filter(NPC.campaign_id == campaign.id).all()


def test_every_starting_npc_gets_a_full_profile_that_stays_the_same(db_session):
    npcs = _village_npcs(db_session)
    assert len(npcs) >= 5

    for npc in npcs:
        first = profile.ensure(db_session, npc)
        assert set(first) == {"temperament", "speech", "habit", "stance", "want", "worry", "secret"}
        assert json.loads(npc.profile_json) == first and npc.age is not None
        assert profile.ensure(db_session, npc) == first

    elder = next(npc for npc in npcs if npc.role == "ancião da vila")
    assert elder.age >= 64


def test_nobody_is_ever_hostile_or_afraid_of_the_transported():
    stances = {profile.generate(random.Random(seed), "ferreira")[1]["stance"] for seed in range(500)}
    assert stances == {"WELCOMING", "CURIOUS", "PRAGMATIC", "DISTRUSTFUL", "OMEN"}


def test_distrust_colours_the_tone_but_never_blocks(db_session):
    npc = _village_npcs(db_session)[0]
    profile.ensure(db_session, npc)
    data = json.loads(npc.profile_json)
    data["stance"] = "DISTRUSTFUL"
    npc.profile_json = json.dumps(data)

    lines = " ".join(profile.context_lines(db_session, npc, trust=0))
    assert "desconfiado" in lines and "they still answer, sell, hire and help" in lines
    assert "Secret" not in lines
    assert data["secret"] in " ".join(profile.context_lines(db_session, npc, trust=profile.SECRET_TRUST))


def test_appearance_follows_age(db_session):
    npc = next(npc for npc in _village_npcs(db_session) if npc.role == "ferreira")
    profile.ensure(db_session, npc)

    npc.age = 19
    assert people_present.npc_appearance_pt(db_session, npc.campaign_id, npc).startswith("moça")
    npc.age = 66
    assert people_present.npc_appearance_pt(db_session, npc.campaign_id, npc).startswith("mulher idosa")
