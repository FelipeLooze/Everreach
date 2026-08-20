from app.ai.context_builder import build_context
from app.ai.intent_parser import Intent
from app.core.enums import ActionIntentType, NPCActivity
from app.db.models.npc import NPC
from app.game import engine
from app.game.game_state import build_game_state
from app.game.npcs import service as npcs_service
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)


def _setup(db_session):
    campaign = create_campaign(
        db_session,
        "NPC Availability",
    )

    _region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    from app.db.models.character import Character

    character = Character(
        campaign_id=campaign.id,
        name="Tester",
        location_id=village.id,
    )

    db_session.add(character)
    db_session.flush()

    return campaign, village, character


def test_resting_npc_is_not_nearby(
    db_session,
):
    campaign, village, character = _setup(db_session)

    npc = (
        db_session.query(NPC)
        .filter(
            NPC.campaign_id == campaign.id,
            NPC.location_id == village.id,
        )
        .first()
    )

    npc.activity = NPCActivity.RESTING.value
    db_session.flush()

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    assert npc.id not in {
        nearby.id
        for nearby in state.nearby_npcs
    }


def test_working_npc_remains_available_for_interaction(
    db_session,
):
    campaign, village, character = _setup(db_session)

    npc = (
        db_session.query(NPC)
        .filter(
            NPC.campaign_id == campaign.id,
            NPC.role == "ferreira",
        )
        .one()
    )

    npc.activity = NPCActivity.WORKING.value
    db_session.flush()

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    assert npc.id in {
        nearby.id
        for nearby in state.nearby_npcs
    }

    intent = Intent(
        type=ActionIntentType.TALK,
        target=npc.name,
        raw_text=f"Falo com {npc.name}.",
    )

    summary, minutes = engine._apply_intent(
        db_session,
        campaign.id,
        character,
        intent,
        state,
    )

    assert npc.name in summary
    assert minutes == 0


def test_resting_npc_cannot_be_talk_target(
    db_session,
):
    campaign, village, character = _setup(db_session)

    npc = (
        db_session.query(NPC)
        .filter(
            NPC.campaign_id == campaign.id,
        )
        .first()
    )

    npc.activity = NPCActivity.RESTING.value
    db_session.flush()

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    intent = Intent(
        type=ActionIntentType.TALK,
        target=npc.name,
        raw_text=f"Falo com {npc.name}.",
    )

    summary, minutes = engine._apply_intent(
        db_session,
        campaign.id,
        character,
        intent,
        state,
    )

    assert "não há ninguém" in summary.casefold()
    assert minutes == 0


def test_resting_npc_clears_active_interlocutor(
    db_session,
):
    campaign, village, character = _setup(db_session)

    npc = (
        db_session.query(NPC)
        .filter(
            NPC.campaign_id == campaign.id,
        )
        .first()
    )

    npcs_service.meet_npc(
        db_session,
        campaign.id,
        character.id,
        npc.id,
    )

    assert (
        npcs_service.get_active_interlocutor(
            db_session,
            campaign.id,
            character.id,
            village.id,
        )
        is not None
    )

    npc.activity = NPCActivity.RESTING.value
    db_session.flush()

    assert (
        npcs_service.get_active_interlocutor(
            db_session,
            campaign.id,
            character.id,
            village.id,
        )
        is None
    )


def test_context_exposes_working_activity(
    db_session,
):
    campaign, _village, character = _setup(db_session)

    blacksmith = (
        db_session.query(NPC)
        .filter(
            NPC.campaign_id == campaign.id,
            NPC.role == "ferreira",
        )
        .one()
    )

    blacksmith.activity = NPCActivity.WORKING.value
    db_session.flush()

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    context = build_context(
        db_session,
        state,
    )

    assert (
        "Mira Draske (ferreira; activity=WORKING)"
        in context
    )