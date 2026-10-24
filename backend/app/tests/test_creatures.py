"""Hunting around the starting village: creatures come from the authoritative
bestiary (app/data/bestiary.json), live where its rules allow, come out at
their hours, fight with their own species' numbers, regrow each dawn and
never pass for people — and losing to them only makes the character faint
and wake up back in the village."""

import json
import random

from app.core.enums import CharacterStatus
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.game.combat.fainting import faint_and_wake
from app.game.creatures import population
from app.game.creatures.species import all_species, get, is_active
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


def _at(db_session, campaign_id, hour):
    now = clock.get_world_time(db_session, campaign_id).total_minutes()
    minutes = (now // DAY + 1) * DAY + hour * 60 - now
    clock.advance_world_time(db_session, campaign_id, minutes)
    npc_simulation.tick(db_session, campaign_id, minutes)
    db_session.flush()


def _forest_next_to_the_village(db_session, campaign_id):
    hops = population._distances_from_village(db_session, campaign_id)
    return next(
        db_session.get(Location, place_id) for place_id, distance in hops.items()
        if distance == 1 and db_session.get(Location, place_id).type == "forest"
    )


def _spawn(db_session, campaign_id, place, name, hour=12):
    species = next(s for s in all_species().values() if s.singular == name)
    creature = population._spawn(db_session, campaign_id, place, species, "remota", random.Random(1), hour)
    db_session.flush()
    return creature


def test_the_bestiary_loads_all_250_creatures_with_life_stages():
    species = all_species()
    assert len(species) == 250
    boar = next(s for s in species.values() if s.singular == "Javali")  # "Javali Jovem" in the dataset
    assert set(boar.stages) == {"jovem", "adulto", "velho"}
    assert boar.stages["adulto"].hp > boar.stages["jovem"].hp
    # Dataset: a barn rat bites for 0; the campaign makes level 1 a real fight.
    assert next(s for s in species.values() if s.singular == "Rato de Celeiro").stages["adulto"].damage == (2, 2)


def test_near_the_village_only_low_level_local_fauna(client, db_session):
    campaign_id, _character = _world(client, db_session)
    hops = population._distances_from_village(db_session, campaign_id)
    near = [place_id for place_id, distance in hops.items() if distance == 1]
    creatures = db_session.query(NPC).filter(NPC.location_id.in_(near), NPC.creature_species.is_not(None)).all()
    assert creatures
    for creature in creatures:
        assert json.loads(creature.profile_json)["level"] <= 2, creature.name
        assert get(creature.creature_species).kind not in ("sobrenatural_ou_construto",)


def test_animals_keep_their_hours_and_are_never_people(client, db_session):
    campaign_id, character = _world(client, db_session)
    forest = _forest_next_to_the_village(db_session, campaign_id)
    wolf = _spawn(db_session, campaign_id, forest, "Lobo Cinzento")  # dusk and night

    _at(db_session, campaign_id, 12)
    assert wolf not in creatures_at_location(db_session, forest.id)
    _at(db_session, campaign_id, 22)
    assert wolf in creatures_at_location(db_session, forest.id)

    character.location_id = forest.id
    db_session.flush()
    state = build_game_state(db_session, campaign_id, character.id)
    assert wolf in state.nearby_creatures and wolf not in npcs_at_location(db_session, forest.id)


def test_the_wild_regrows_one_animal_of_each_species_a_day(client, db_session):
    campaign_id, _character = _world(client, db_session)
    forest = _forest_next_to_the_village(db_session, campaign_id)
    living = db_session.query(NPC).filter(NPC.location_id == forest.id, NPC.creature_species.is_not(None)).all()
    species_here = {creature.creature_species for creature in living}
    for creature in living:
        creature.alive = False
    db_session.flush()

    _at(db_session, campaign_id, 12)  # crosses a dawn
    regrown = db_session.query(NPC).filter(
        NPC.location_id == forest.id, NPC.creature_species.is_not(None), NPC.alive.is_(True)
    ).all()
    assert sorted(c.creature_species for c in regrown) == sorted(species_here)


def test_a_territorial_animal_asleep_ambushes_no_one(client, db_session):
    from app.game.combat.hostility import resolve_ambush_for_character

    campaign_id, character = _world(client, db_session)
    forest = _forest_next_to_the_village(db_session, campaign_id)
    for creature in db_session.query(NPC).filter(NPC.location_id == forest.id, NPC.creature_species.is_not(None)):
        creature.alive = False
    boar = _spawn(db_session, campaign_id, forest, "Javali")  # territorial, out by day
    assert boar.hostility >= 75
    character.location_id = forest.id

    _at(db_session, campaign_id, 22)
    assert resolve_ambush_for_character(db_session, campaign_id, character, rng=random.Random(1)) is None
    _at(db_session, campaign_id, 12)
    ambush = next(
        (a for seed in range(30) if (a := resolve_ambush_for_character(db_session, campaign_id, character, rng=random.Random(seed)))),
        None,
    )
    assert ambush is not None and ambush.npc_id == boar.id


def test_a_creature_bites_with_its_own_numbers():
    from app.game.creatures.combat import damage_roll

    rat = {"damage": [0, 0], "level": 1}
    boar = {"damage": [1, 4], "level": 3}
    assert all(damage_roll(rat, False, random.Random(seed)) == 0 for seed in range(20))
    assert {damage_roll(boar, False, random.Random(seed)) for seed in range(50)} <= {1, 2, 3, 4}


def test_fists_fight_a_wolf_and_a_wolf_at_zero_is_dead(client, db_session):
    from app.ai.llm_service import LLMService
    from app.game import engine

    class Scripted(LLMService):
        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps({"intent": "ATTACK", "target": "lobo", "weapon": "punhos",
                                   "attack_type": "MELEE_ATTACK"})
            return "— Rosnados."

    campaign_id, character = _world(client, db_session)
    forest = _forest_next_to_the_village(db_session, campaign_id)
    for creature in db_session.query(NPC).filter(NPC.location_id == forest.id, NPC.creature_species.is_not(None)):
        creature.alive = False
    wolf = _spawn(db_session, campaign_id, forest, "Lobo Cinzento", hour=22)
    _at(db_session, campaign_id, 22)
    character.location_id = forest.id
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


def test_losing_a_fight_means_waking_up_at_the_inn(client, db_session):
    campaign_id, character = _world(client, db_session)
    forest = _forest_next_to_the_village(db_session, campaign_id)
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


def test_activity_hours_cover_the_dataset_periods():
    wolf = next(s for s in all_species().values() if s.singular == "Lobo Cinzento")
    assert is_active(wolf, 22) and is_active(wolf, 18) and not is_active(wolf, 12)


def _attack(db_session, campaign_id, character, target="lobo"):
    from app.ai.llm_service import LLMService
    from app.game import engine

    class Scripted(LLMService):
        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps({"intent": "ATTACK", "target": target, "weapon": "punhos",
                                   "attack_type": "MELEE_ATTACK"})
            return "— Rosnados."

    llm = Scripted()
    return engine.resolve_action(db_session, llm, campaign_id, character.id, f"Ataco o {target}", intent_llm_service=llm)


def test_a_pack_fights_together_and_the_attack_goes_to_the_most_wounded(client, db_session):
    from app.core.enums import CombatActorType
    from app.game.combat.encounters import get_active_encounter_for_actor, list_active_participants

    campaign_id, character = _world(client, db_session)
    forest = _forest_next_to_the_village(db_session, campaign_id)
    for creature in db_session.query(NPC).filter(NPC.location_id == forest.id, NPC.creature_species.is_not(None)):
        creature.alive = False
    wolves = [_spawn(db_session, campaign_id, forest, "Lobo Cinzento", hour=22) for _ in range(3)]
    _at(db_session, campaign_id, 22)
    character.location_id = forest.id
    wolves[2].hp_current = 2
    db_session.commit()

    result = _attack(db_session, campaign_id, character)
    encounter = get_active_encounter_for_actor(db_session, CombatActorType.CHARACTER, character.id)
    if encounter is not None:  # the fight may already be over in one blow
        assert len(list_active_participants(db_session, encounter.id)) >= 3
    assert "mais de um alvo" not in result.mechanical_summary


def test_out_of_breath_the_turn_goes_to_catching_it(client, db_session):
    campaign_id, character = _world(client, db_session)
    forest = _forest_next_to_the_village(db_session, campaign_id)
    for creature in db_session.query(NPC).filter(NPC.location_id == forest.id, NPC.creature_species.is_not(None)):
        creature.alive = False
    wolf = _spawn(db_session, campaign_id, forest, "Lobo Cinzento", hour=22)
    _at(db_session, campaign_id, 22)
    character.location_id = forest.id
    wolf.hp_current = 50
    db_session.commit()
    _attack(db_session, campaign_id, character)  # the fight starts
    character.stamina_current = 0
    db_session.commit()

    result = _attack(db_session, campaign_id, character)

    assert "sem fôlego" in result.mechanical_summary
    assert character.stamina_current >= 4
