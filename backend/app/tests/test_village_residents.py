"""Starting village, part 2: about 15 residents with homes and routines, so
who is in the square, the inn or the forge changes with the hour."""

from app.db.models.location import Location
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.npcs import residents
from app.game.npcs.service import npcs_at_location
from app.game.time import clock
from app.game.world.generator import gender_for_name
from app.simulation import npc_simulation

DAY = 24 * 60


def _world(db_session):
    from app.game.world.seed import create_campaign, seed_initial_region

    campaign = create_campaign(db_session, "Moradores")
    region, village = seed_initial_region(db_session, campaign.id)
    create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.flush()
    return campaign, village


def _at(db_session, campaign_id, hour):
    now = clock.get_world_time(db_session, campaign_id).total_minutes()
    target = (now // DAY + 1) * DAY + hour * 60
    clock.advance_world_time(db_session, campaign_id, target - now)
    npc_simulation.tick(db_session, campaign_id, 1)
    db_session.flush()


def _service(db_session, village, service_type):
    return db_session.query(Location).filter(
        Location.parent_location_id == village.id, Location.type == service_type
    ).one()


def _resident(db_session, campaign_id, role_prefix):
    return next(
        npc for npc in db_session.query(NPC).filter(NPC.campaign_id == campaign_id, NPC.routine_json != "[]")
        if npc.role.startswith(role_prefix)
    )


def test_the_village_has_about_fifteen_residents_with_distinct_first_names(db_session):
    campaign, village = _world(db_session)
    people = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.location_id == village.id).all()
    living_here = [npc for npc in people if npc.routine_json != "[]"]

    assert len(living_here) == len(residents.RESIDENTS) == 15
    first_names = [npc.name.split()[0] for npc in people]
    assert len(first_names) == len(set(first_names))
    for npc in living_here:
        assert npc.age is not None and npc.profile_json != "{}"
        feminine_role = npc.role.split()[0].endswith(("a", "ã")) and not npc.role.startswith(("guarda", "lojista", "herbalista", "aprendiz"))
        if feminine_role:
            assert gender_for_name(npc.name) == "F", npc.role


def test_who_is_where_changes_with_the_hour(db_session):
    campaign, village = _world(db_session)
    inn = _service(db_session, village, "inn")
    forge = _service(db_session, village, "blacksmith")
    apprentice = _resident(db_session, campaign.id, "aprendiz")
    cook = _resident(db_session, campaign.id, "cozinheir")

    _at(db_session, campaign.id, 10)
    assert apprentice in npcs_at_location(db_session, forge.id)
    assert cook in npcs_at_location(db_session, inn.id)
    morning_square = npcs_at_location(db_session, village.id)

    _at(db_session, campaign.id, 12)
    assert apprentice in npcs_at_location(db_session, inn.id)  # lunch at the inn

    _at(db_session, campaign.id, 19)
    evening_inn = npcs_at_location(db_session, inn.id)
    assert len(evening_inn) > 3 and apprentice in evening_inn

    _at(db_session, campaign.id, 3)
    awake = [npc for npc in npcs_at_location(db_session, village.id) if npc.routine_json != "[]"]
    assert all(npc.role.startswith("guarda") or npc.role.startswith("beberr") for npc in awake)
    assert morning_square != npcs_at_location(db_session, village.id)


def test_the_hunter_is_in_the_forest_by_day(db_session):
    campaign, village = _world(db_session)
    hunter = _resident(db_session, campaign.id, "caçador")

    _at(db_session, campaign.id, 9)
    forest = db_session.get(Location, hunter.workplace_location_id)
    assert forest.type == "forest" and hunter in npcs_at_location(db_session, forest.id)
    _at(db_session, campaign.id, 12)
    assert hunter in npcs_at_location(db_session, village.id)


def test_waiting_passes_the_time_the_player_asked_for():
    from app.game.engine import _wait_minutes

    assert _wait_minutes("Espero um pouco", 10, 0) == 15
    assert _wait_minutes("Espero até o fim da tarde, observando o movimento", 10, 0) == 8 * 60
    assert _wait_minutes("Aguardo duas horas", 10, 0) == 120
    assert _wait_minutes("espero meia hora", 10, 0) == 30
    assert _wait_minutes("Espero até o amanhecer", 22, 30) == 7 * 60 + 30
    assert _wait_minutes("Fico esperando até a noite", 18, 30) == 30


def test_an_unmet_npc_is_never_named_to_the_narrator(db_session):
    from app.ai.context_builder import _npc_label
    from app.db.models.character import Character
    from app.game.relationships.service import record_npc_interaction

    campaign, village = _world(db_session)
    character = db_session.query(Character).one()
    cook = _resident(db_session, campaign.id, "cozinheir")

    assert cook.name not in _npc_label(db_session, character, cook)
    record_npc_interaction(db_session, campaign.id, character.id, cook.id)
    assert _npc_label(db_session, character, cook) == cook.name


def test_young_residents_never_look_old(db_session):
    from app.game.npcs import looks

    campaign, _village = _world(db_session)
    for npc in db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.creature_species.is_(None)):
        traits = looks.ensure(db_session, npc)
        if npc.age < 40:
            assert traits["hair_color"] not in ("grey hair", "white hair", "silver hair"), npc.role
        if npc.age < 18:
            assert "facial_hair" not in traits, npc.role
