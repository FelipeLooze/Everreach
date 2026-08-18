from app.db.models.npc import NPC
from app.core.enums import EventType
from app.db.models.event import WorldEvent
from app.simulation import development_simulation
from app.game.time.clock import advance_world_time
from app.game.character.service import (
    create_character,
)
from app.game.developments.service import (
    create_world_development,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)
from app.game.developments.knowledge import (
    local_character_witnesses,
    local_npc_witnesses,
)
from app.db.models.knowledge import (
    KnowledgeFact,
    KnowledgeKnower,
)
from app.core.enums import (
    CharacterStatus,
    EventType,
    KnowledgeCertainty,
    KnowerType,
    NPCActivity,
    WorldDevelopmentType,
)

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

def test_local_npc_witnesses_learn_development_fact_by_direct_perception(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Witness Knowledge",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    witness = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Witness",
        activity=NPCActivity.RESTING.value,
    )

    dead_npc = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Dead Witness",
        alive=False,
    )

    db_session.add_all(
        [
            witness,
            dead_npc,
        ]
    )
    db_session.flush()

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Nova torre",
        interval_minutes=7 * 24 * 60,
        payload={
            "progress": 0,
            "progress_per_update": 10,
        },
        location_id=location.id,
    )

    fact = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.subject
            == f"world_development:{development.id}"
        )
        .one()
    )

    witness_link = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == witness.id,
        )
        .one()
    )

    assert (
        witness_link.source
        == "percepção direta"
    )

    assert (
        witness_link.certainty
        == KnowledgeCertainty.CONFIRMED.value
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_id
            == dead_npc.id,
        )
        .count()
        == 0
    )

    propagated_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.KNOWLEDGE_PROPAGATED.value
        )
        .count()
    )

    assert propagated_events == 0

def test_local_character_witness_learns_development_fact_by_direct_perception(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Player Witness",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    witness = create_character(
        db_session,
        campaign.id,
        "Present Character",
        region.id,
        location.id,
    )

    dead_character = create_character(
        db_session,
        campaign.id,
        "Dead Character",
        region.id,
        location.id,
    )

    dead_character.status = (
        CharacterStatus.DEAD.value
    )

    absent_character = create_character(
        db_session,
        campaign.id,
        "Absent Character",
        region.id,
        None,
    )

    db_session.flush()

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Muralha nova",
        interval_minutes=7 * 24 * 60,
        payload={
            "progress": 0,
            "progress_per_update": 10,
        },
        location_id=location.id,
    )

    fact = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.subject
            == f"world_development:{development.id}"
        )
        .one()
    )

    witness_link = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id
            == witness.id,
        )
        .one()
    )

    assert (
        witness_link.source
        == "percepção direta"
    )

    assert (
        witness_link.certainty
        == KnowledgeCertainty.CONFIRMED.value
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id
            == dead_character.id,
        )
        .count()
        == 0
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id
            == absent_character.id,
        )
        .count()
        == 0
    )

    propagated_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.KNOWLEDGE_PROPAGATED.value
        )
        .count()
    )

    assert propagated_events == 0

def test_local_character_witnesses_returns_only_alive_characters_at_location(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Character Witness Selection",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    present = create_character(
        db_session,
        campaign.id,
        "Present",
        region.id,
        location.id,
    )

    dead = create_character(
        db_session,
        campaign.id,
        "Dead",
        region.id,
        location.id,
    )

    dead.status = CharacterStatus.DEAD.value

    absent = create_character(
        db_session,
        campaign.id,
        "Absent",
        region.id,
        None,
    )

    db_session.flush()

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Mercado novo",
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

    witnesses = local_character_witnesses(
        db_session,
        event,
    )

    witness_ids = {
        character.id
        for character in witnesses
    }

    assert present.id in witness_ids
    assert dead.id not in witness_ids
    assert absent.id not in witness_ids

def test_historical_catch_up_does_not_use_current_location_as_direct_perception(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Historical Witness",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    witness = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Historical Witness",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add(witness)
    db_session.flush()

    interval = 7 * 24 * 60

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Ponte histórica",
        interval_minutes=interval,
        payload={
            "progress": 0,
            "progress_per_update": 10,
        },
        location_id=location.id,
    )

    # A criação acontece no presente e pode ser percebida.
    creation_fact = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.subject
            == f"world_development:{development.id}",
            KnowledgeFact.statement
            == "Ponte histórica começou.",
        )
        .one()
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id
            == creation_fact.id,
            KnowledgeKnower.knower_id
            == witness.id,
        )
        .count()
        == 1
    )

    # Pulamos dois intervalos de uma vez.
    # O primeiro update será histórico;
    # o segundo ocorre exatamente no tempo atual.
    advance_world_time(
        db_session,
        campaign.id,
        2 * interval,
    )

    development_simulation.tick(
        db_session,
        campaign.id,
        2 * interval,
    )

    db_session.flush()

    historical_fact = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.subject
            == f"world_development:{development.id}",
            KnowledgeFact.statement
            == "Ponte histórica atingiu 10% de progresso.",
        )
        .one()
    )

    current_fact = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.subject
            == f"world_development:{development.id}",
            KnowledgeFact.statement
            == "Ponte histórica atingiu 20% de progresso.",
        )
        .one()
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id
            == historical_fact.id,
            KnowledgeKnower.knower_id
            == witness.id,
        )
        .count()
        == 0
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id
            == current_fact.id,
            KnowledgeKnower.knower_id
            == witness.id,
        )
        .count()
        == 1
    )