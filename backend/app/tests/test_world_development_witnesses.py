from app.core.enums import (
    NPCActivity,
    WorldDevelopmentType,
)
from app.db.models.npc import NPC
from app.game.developments.knowledge import (
    local_npc_witnesses,
)
from app.game.developments.service import (
    create_world_development,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)
from app.db.models.event import WorldEvent
from app.core.enums import EventType


def test_local_npc_witnesses_returns_alive_npcs_at_event_location(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Local Witnesses",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    awake = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Awake",
        activity=NPCActivity.AVAILABLE.value,
    )

    resting = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Resting",
        activity=NPCActivity.RESTING.value,
    )

    dead = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Dead",
        alive=False,
    )

    db_session.add_all(
        [
            awake,
            resting,
            dead,
        ]
    )
    db_session.flush()

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Nova ponte",
        interval_minutes=7 * 24 * 60,
        payload={
            "progress": 0,
            "progress_per_update": 10,
        },
        location_id=location.id,
    )

    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.actor_id == development.id,
            WorldEvent.event_type
            == EventType.WORLD_DEVELOPMENT_CREATED.value,
        )
        .one()
    )

    witnesses = local_npc_witnesses(
        db_session,
        event,
    )

    witness_ids = {
        npc.id
        for npc in witnesses
    }

    assert awake.id in witness_ids
    assert resting.id in witness_ids
    assert dead.id not in witness_ids

def test_local_npc_witnesses_returns_empty_without_location(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Regional Development",
    )

    event = WorldEvent(
        campaign_id=campaign.id,
        event_type=(
            EventType.WORLD_DEVELOPMENT_CREATED.value
        ),
        actor_type="world_development",
        actor_id="dev_regional",
        payload_json="{}",
        world_minute=0,
        importance=1,
    )

    db_session.add(event)
    db_session.flush()

    assert (
        local_npc_witnesses(
            db_session,
            event,
        )
        == []
    )