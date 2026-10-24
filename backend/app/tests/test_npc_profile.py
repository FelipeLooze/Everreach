"""Starting village, part 1: every NPC has a structured personality, and
toward transported people nobody goes past distrustful (2026-10-24)."""

import json
import random

from app.ai import people_present
from app.db.models.character import Character
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


def test_every_npc_gets_a_full_look_matching_age_and_trade(db_session):
    from app.game.npcs import looks

    for npc in _village_npcs(db_session):
        traits = looks.ensure(db_session, npc)
        assert {"height", "build", "hair_style", "skin", "mark", "outfit"} <= set(traits)
        if npc.age >= 60:
            assert traits["hair_color"] in ("grey hair", "white hair", "silver hair")
        if npc.role == "ferreira":
            assert traits["build"] not in ("thin", "frail", "wiry", "stooped")
            assert "avental de couro" in people_present.npc_appearance_pt(db_session, npc.campaign_id, npc)


def test_the_player_can_point_at_someone_by_a_distinctive_mark(db_session):
    from app.game.game_state import build_game_state
    from app.game.npcs import looks
    from app.game.visual.npc import set_npc_stable_identity

    _village_npcs(db_session)
    character = db_session.query(Character).one()
    state = build_game_state(db_session, character.campaign_id, character.id)
    present = [npc for kind, npc in people_present.present_people(state) if kind == "npc"]
    assert len(present) >= 2
    for npc in present:
        looks.ensure(db_session, npc)
        set_npc_stable_identity(db_session, npc.campaign_id, npc.id, {"mark": "a crooked nose"})
    target = present[0]
    set_npc_stable_identity(db_session, target.campaign_id, target.id, {"mark": "a scar across the chin"})

    assert "com uma cicatriz no queixo" in people_present.npc_appearance_pt(db_session, target.campaign_id, target)
    assert people_present.match_by_appearance(db_session, state, "Vou falar com a pessoa da cicatriz") == ("npc", target)
