"""Hunting around the starting village, part A1: animals live in the wild
places, come out at their hours, attack or not by species, regrow each dawn,
never pass for people — and losing to them only makes the character faint
and wake up back in the village."""

from app.core.enums import CharacterStatus, NPCActivity
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.game.combat.fainting import faint_and_wake
from app.game.creatures import population
from app.game.game_state import build_game_state
from app.game.npcs.service import creatures_at_location, npcs_at_location
from app.game.time import clock
from app.simulation import npc_simulation

DAY = 24 * 60


def _world(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Caça"}).json()
    data = client.post(f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}).json()
    client.post(f"/api/campaigns/{campaign['id']}/start", params={"character_id": data["id"]})
    return campaign["id"], db_session.get(Character, data["id"])


def _place(db_session, campaign_id, location_type):
    return next(
        npc_place for npc_place in db_session.query(Location).filter(Location.type == location_type)
        if db_session.query(NPC).filter(NPC.location_id == npc_place.id, NPC.creature_species.is_not(None)).count()
    )


def _at(db_session, campaign_id, hour):
    now = clock.get_world_time(db_session, campaign_id).total_minutes()
    minutes = (now // DAY + 1) * DAY + hour * 60 - now
    clock.advance_world_time(db_session, campaign_id, minutes)
    npc_simulation.tick(db_session, campaign_id, minutes)
    db_session.flush()


def _species_here(db_session, location_id):
    return sorted(creature.creature_species for creature in creatures_at_location(db_session, location_id))


def test_the_wild_is_populated_and_animals_keep_their_hours(client, db_session):
    campaign_id, _character = _world(client, db_session)
    forest = _place(db_session, campaign_id, "forest")

    _at(db_session, campaign_id, 12)
    assert "boar" in _species_here(db_session, forest.id) and "wolf" not in _species_here(db_session, forest.id)
    _at(db_session, campaign_id, 22)
    assert "wolf" in _species_here(db_session, forest.id) and "boar" not in _species_here(db_session, forest.id)


def test_animals_are_never_people(client, db_session):
    campaign_id, character = _world(client, db_session)
    forest = _place(db_session, campaign_id, "forest")
    _at(db_session, campaign_id, 22)
    character.location_id = forest.id
    db_session.flush()

    state = build_game_state(db_session, campaign_id, character.id)
    assert state.nearby_creatures and not any(npc.creature_species for npc in npcs_at_location(db_session, forest.id))
    assert all(creature.profile_json == "{}" for creature in state.nearby_creatures)


def test_the_wild_regrows_one_animal_a_day(client, db_session):
    campaign_id, _character = _world(client, db_session)
    clearing = _place(db_session, campaign_id, "clearing")
    wolves = db_session.query(NPC).filter(NPC.location_id == clearing.id, NPC.creature_species == "wolf").all()
    assert len(wolves) == 3
    for wolf in wolves:
        wolf.alive = False
    db_session.flush()

    _at(db_session, campaign_id, 12)  # crosses a dawn
    alive = db_session.query(NPC).filter(
        NPC.location_id == clearing.id, NPC.creature_species == "wolf", NPC.alive.is_(True)
    ).count()
    assert alive == 1


def test_a_wolf_asleep_in_its_den_ambushes_no_one(client, db_session):
    import random

    from app.game.combat.hostility import resolve_ambush_for_character

    campaign_id, character = _world(client, db_session)
    forest = _place(db_session, campaign_id, "forest")
    character.location_id = forest.id
    _at(db_session, campaign_id, 12)
    for boar in db_session.query(NPC).filter(NPC.location_id == forest.id, NPC.creature_species == "boar"):
        boar.alive = False  # only the sleeping wolves remain
    db_session.flush()

    assert resolve_ambush_for_character(db_session, campaign_id, character, rng=random.Random(1)) is None
    _at(db_session, campaign_id, 22)
    ambush = None
    for seed in range(20):
        ambush = resolve_ambush_for_character(db_session, campaign_id, character, rng=random.Random(seed))
        if ambush:
            break
    assert ambush is not None and "Lobo" in ambush.npc_name


def test_losing_a_fight_means_waking_up_at_the_inn(client, db_session):
    campaign_id, character = _world(client, db_session)
    forest = _place(db_session, campaign_id, "forest")
    character.location_id = forest.id
    character.status = CharacterStatus.INCAPACITATED.value
    character.hp_current = 0
    before = clock.get_world_time(db_session, campaign_id).total_minutes()

    summary = faint_and_wake(db_session, campaign_id, character)

    inn = db_session.get(Location, character.location_id)
    assert inn.type == "inn" and character.status == CharacterStatus.ALIVE.value
    assert 0 < character.hp_current < character.hp_max
    assert clock.get_world_time(db_session, campaign_id).total_minutes() - before == 4 * 60
    assert "desmaia" in summary and inn.name in summary


def test_fists_fight_a_wolf_and_a_wolf_at_zero_is_dead(client, db_session):
    import json

    from app.ai.llm_service import LLMService
    from app.game import engine

    class Scripted(LLMService):
        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps({"intent": "ATTACK", "target": "lobo", "weapon": "punhos",
                                   "attack_type": "MELEE_ATTACK"})
            return "— Rosnados."

    campaign_id, character = _world(client, db_session)
    forest = _place(db_session, campaign_id, "forest")
    _at(db_session, campaign_id, 22)
    character.location_id = forest.id
    wolf = next(c for c in creatures_at_location(db_session, forest.id) if c.creature_species == "wolf")
    for other in creatures_at_location(db_session, forest.id):
        if other is not wolf:
            other.alive = False
    wolf.hp_current = 1
    db_session.commit()

    llm = Scripted()
    for _ in range(12):
        result = engine.resolve_action(db_session, llm, campaign_id, character.id, "Ataco o lobo com os punhos", intent_llm_service=llm)
        assert "não está equipado" not in result.mechanical_summary
        db_session.refresh(wolf)
        if not wolf.alive:
            break
    assert wolf.alive is False
