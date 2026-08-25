"""Simplification Pass S1.2 — NPC workplace/default presence.

Confirmed by the S0 audit: NPC.location_id is set once at world-seed
(always the settlement hub) and never written again by any production
code path. An innkeeper/blacksmith seeded this way was never actually
findable at their own inn/forge — a player physically inside the service
Location found nobody there, and the narrator invented a replacement
person. Fixed with a new, optional NPC.workplace_location_id (nullable,
additive) and an effective-location read in npcs_at_location: WORKING +
a set workplace resolves there; everything else is unchanged.
"""
from app.core.enums import NPCActivity
from app.db.models.character import Character
from app.db.models.npc import NPC
from app.game.game_state import build_game_state
from app.game.npcs.service import npcs_at_location
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session, name="NPC Workplace"):
    campaign = create_campaign(db_session, name)
    region, village = seed_initial_region(db_session, campaign.id)
    character = Character(
        campaign_id=campaign.id, name="Tester", region_id=region.id, location_id=village.id
    )
    db_session.add(character)
    db_session.flush()
    return campaign, village, character


def _npc_by_role(db_session, campaign_id, role):
    return (
        db_session.query(NPC)
        .filter(NPC.campaign_id == campaign_id, NPC.role == role)
        .one()
    )


# --- seeding: exact linkage set at generation time ---


def test_seeded_innkeeper_has_a_workplace_location_id(db_session):
    campaign, village, _character = _setup(db_session, "S1.2 Innkeeper Seed")
    innkeeper = _npc_by_role(db_session, campaign.id, "estalajadeiro")
    assert innkeeper.workplace_location_id is not None
    assert innkeeper.workplace_location_id != village.id
    assert innkeeper.location_id == village.id  # base/home location unchanged


def test_seeded_blacksmith_has_a_workplace_location_id(db_session):
    campaign, village, _character = _setup(db_session, "S1.2 Blacksmith Seed")
    blacksmith = _npc_by_role(db_session, campaign.id, "ferreira")
    assert blacksmith.workplace_location_id is not None
    assert blacksmith.workplace_location_id != village.id
    assert blacksmith.location_id == village.id


def test_elder_has_no_workplace_override_stays_at_hub(db_session):
    # No service-location role match — the elder's base location_id (the
    # village square) already IS where they're narratively expected.
    campaign, village, _character = _setup(db_session, "S1.2 Elder Seed")
    elder = _npc_by_role(db_session, campaign.id, "ancião da vila")
    assert elder.workplace_location_id is None
    assert elder.location_id == village.id


def test_workplace_is_the_actual_inn_location_not_a_different_service(db_session):
    from app.db.models.location import Location

    campaign, _village, _character = _setup(db_session, "S1.2 Workplace Identity")
    innkeeper = _npc_by_role(db_session, campaign.id, "estalajadeiro")
    workplace = db_session.get(Location, innkeeper.workplace_location_id)
    assert workplace.type == "inn"


# --- effective presence ---


def test_working_innkeeper_is_found_at_the_inn_not_the_hub(db_session):
    campaign, village, _character = _setup(db_session, "S1.2 Innkeeper Presence")
    innkeeper = _npc_by_role(db_session, campaign.id, "estalajadeiro")
    innkeeper.activity = NPCActivity.WORKING.value
    db_session.flush()

    at_inn = npcs_at_location(db_session, innkeeper.workplace_location_id)
    at_hub = npcs_at_location(db_session, village.id)

    assert innkeeper.id in {n.id for n in at_inn}
    assert innkeeper.id not in {n.id for n in at_hub}


def test_working_blacksmith_is_found_at_the_forge_not_the_hub(db_session):
    campaign, village, _character = _setup(db_session, "S1.2 Blacksmith Presence")
    blacksmith = _npc_by_role(db_session, campaign.id, "ferreira")
    blacksmith.activity = NPCActivity.WORKING.value
    db_session.flush()

    at_forge = npcs_at_location(db_session, blacksmith.workplace_location_id)
    at_hub = npcs_at_location(db_session, village.id)

    assert blacksmith.id in {n.id for n in at_forge}
    assert blacksmith.id not in {n.id for n in at_hub}


def test_non_working_innkeeper_stays_at_the_hub(db_session):
    # AVAILABLE (not WORKING) never triggers the workplace override, even
    # though workplace_location_id is set — matches the spec's own rule
    # ("activity == WORKING and workplace exists").
    campaign, village, _character = _setup(db_session, "S1.2 Not Working")
    innkeeper = _npc_by_role(db_session, campaign.id, "estalajadeiro")
    innkeeper.activity = NPCActivity.AVAILABLE.value
    db_session.flush()

    at_inn = npcs_at_location(db_session, innkeeper.workplace_location_id)
    at_hub = npcs_at_location(db_session, village.id)

    assert innkeeper.id not in {n.id for n in at_inn}
    assert innkeeper.id in {n.id for n in at_hub}


def test_npc_without_a_workplace_keeps_normal_location_even_while_working(db_session):
    # An NPC with no linked workplace (e.g. the elder, or any future NPC
    # whose role has no obvious service mapping) is unaffected by this
    # phase even if something externally sets activity=WORKING on them.
    campaign, village, _character = _setup(db_session, "S1.2 No Workplace")
    elder = _npc_by_role(db_session, campaign.id, "ancião da vila")
    elder.activity = NPCActivity.WORKING.value
    db_session.flush()

    at_hub = npcs_at_location(db_session, village.id)
    assert elder.id in {n.id for n in at_hub}


def test_npc_is_never_present_at_both_hub_and_workplace_simultaneously(db_session):
    campaign, village, _character = _setup(db_session, "S1.2 No Duplication")
    innkeeper = _npc_by_role(db_session, campaign.id, "estalajadeiro")
    innkeeper.activity = NPCActivity.WORKING.value
    db_session.flush()

    at_inn = {n.id for n in npcs_at_location(db_session, innkeeper.workplace_location_id)}
    at_hub = {n.id for n in npcs_at_location(db_session, village.id)}
    assert not (at_inn & at_hub & {innkeeper.id})


def test_resting_innkeeper_is_visible_nowhere_workplace_does_not_override_rest(
    db_session,
):
    campaign, village, _character = _setup(db_session, "S1.2 Resting Overrides Work")
    innkeeper = _npc_by_role(db_session, campaign.id, "estalajadeiro")
    innkeeper.activity = NPCActivity.RESTING.value
    db_session.flush()

    at_inn = npcs_at_location(db_session, innkeeper.workplace_location_id)
    at_hub = npcs_at_location(db_session, village.id)
    assert innkeeper.id not in {n.id for n in at_inn}
    assert innkeeper.id not in {n.id for n in at_hub}


# --- narrator context sees the correct people ---


def test_narrator_context_sees_the_innkeeper_when_character_enters_the_inn(db_session):
    from app.ai.context_builder import build_context

    campaign, _village, character = _setup(db_session, "S1.2 Narrator Context")
    innkeeper = _npc_by_role(db_session, campaign.id, "estalajadeiro")
    innkeeper.activity = NPCActivity.WORKING.value
    character.location_id = innkeeper.workplace_location_id
    db_session.flush()

    state = build_game_state(db_session, campaign.id, character.id)
    assert innkeeper.id in {n.id for n in state.nearby_npcs}

    context = build_context(db_session, state)
    assert innkeeper.name in context


# --- integration: the exact reported reproduction scenario ---


def test_travel_to_inn_finds_the_real_innkeeper_without_creating_a_new_npc(db_session):
    from app.ai.intent_parser import Intent
    from app.core.enums import ActionIntentType, DiscoveryStatus
    from app.db.models.location import LocationConnection
    from app.game import engine
    from app.game.character.service import create_character
    from app.game.discovery.service import discover_connection, set_location_discovery

    campaign = create_campaign(db_session, "S1.2 Travel Integration")
    region, village = seed_initial_region(db_session, campaign.id)
    # Movement resolution needs real attributes (encumbrance); the shared
    # _setup() helper above deliberately stays minimal for the other
    # presence-only tests in this file, so this one test builds its own
    # fully-attributed character via the established production helper.
    character = create_character(db_session, campaign.id, "Tester", region.id, village.id)
    db_session.commit()
    innkeeper = _npc_by_role(db_session, campaign.id, "estalajadeiro")
    innkeeper.activity = NPCActivity.WORKING.value
    db_session.flush()

    # A real player session reaches this via "olhar ao redor" first; this
    # test drives the discovery layer directly so it isolates the NPC
    # presence fix rather than re-testing exploration.
    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == innkeeper.workplace_location_id,
        )
        .one()
    )
    discover_connection(db_session, character.id, connection.id)
    set_location_discovery(
        db_session, character.id, innkeeper.workplace_location_id, DiscoveryStatus.DISCOVERED
    )

    npc_count_before = db_session.query(NPC).filter(NPC.campaign_id == campaign.id).count()

    state = build_game_state(db_session, campaign.id, character.id)
    move_intent = Intent(
        type=ActionIntentType.MOVE,
        target="Estalagem",
        raw_text="Logan vai em direção à estalagem",
    )
    engine._apply_intent(db_session, campaign.id, character, move_intent, state)
    db_session.flush()

    assert character.location_id == innkeeper.workplace_location_id

    npc_count_after = db_session.query(NPC).filter(NPC.campaign_id == campaign.id).count()
    assert npc_count_after == npc_count_before  # no phantom NPC was created

    state_at_inn = build_game_state(db_session, campaign.id, character.id)
    assert innkeeper.id in {n.id for n in state_at_inn.nearby_npcs}
