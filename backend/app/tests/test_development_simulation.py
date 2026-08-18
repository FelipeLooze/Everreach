import json
from app.simulation import development_simulation
from app.db.models.world_development import WorldDevelopment
from app.db.models.knowledge import KnowledgeFact
from app.game.time.clock import get_world_time
from app.game.world.seed import create_campaign
from app.db.models.event import WorldEvent
from app.core.enums import (
    EventType,
    WorldDevelopmentStatus,
    WorldDevelopmentType,
)

def test_development_simulation_currently_makes_no_changes(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Tick",
    )

    result = development_simulation.tick(
        db_session,
        campaign.id,
        60,
    )

    assert result.changes == 0


def test_development_simulation_ignores_non_positive_time(
    db_session,
):
    zero = development_simulation.tick(
        db_session,
        "campaign_test",
        0,
    )

    negative = development_simulation.tick(
        db_session,
        "campaign_test",
        -10,
    )

    assert zero.changes == 0
    assert negative.changes == 0

def test_due_developments_returns_active_development_due_now(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Due Development",
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    development = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Desenvolvimento vencido",
        next_update_world_minute=now,
    )

    db_session.add(development)
    db_session.flush()

    due = development_simulation.due_developments(
        db_session,
        campaign.id,
    )

    assert [item.id for item in due] == [
        development.id
    ]


def test_due_developments_excludes_not_due_or_ineligible_entries(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Filters",
    )

    other_campaign = create_campaign(
        db_session,
        "Other Campaign",
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    due = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Devido",
        next_update_world_minute=now,
    )

    future = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Futuro",
        next_update_world_minute=now + 60,
    )

    planned = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.PLANNED.value,
        title="Planejado",
        next_update_world_minute=now,
    )

    unscheduled = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Sem agendamento",
        next_update_world_minute=None,
    )

    other = WorldDevelopment(
        campaign_id=other_campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Outra campanha",
        next_update_world_minute=now,
    )

    db_session.add_all(
        [
            due,
            future,
            planned,
            unscheduled,
            other,
        ]
    )
    db_session.flush()

    result = development_simulation.due_developments(
        db_session,
        campaign.id,
    )

    assert [item.id for item in result] == [
        due.id
    ]


def test_due_developments_are_returned_in_deterministic_order(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Order",
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    later = WorldDevelopment(
        id="dev_c",
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Mais tarde",
        next_update_world_minute=now,
    )

    second = WorldDevelopment(
        id="dev_b",
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Segundo",
        next_update_world_minute=now - 60,
    )

    first = WorldDevelopment(
        id="dev_a",
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Primeiro",
        next_update_world_minute=now - 60,
    )

    db_session.add_all(
        [
            later,
            second,
            first,
        ]
    )
    db_session.flush()

    result = development_simulation.due_developments(
        db_session,
        campaign.id,
    )

    assert [item.id for item in result] == [
        "dev_a",
        "dev_b",
        "dev_c",
    ]

def test_development_tick_processes_due_entries_and_counts_only_changes(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Development Processing",
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    first = WorldDevelopment(
        id="dev_a",
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Primeiro",
        next_update_world_minute=now,
    )

    second = WorldDevelopment(
        id="dev_b",
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Segundo",
        next_update_world_minute=now,
    )

    third = WorldDevelopment(
        id="dev_c",
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Terceiro",
        next_update_world_minute=now,
    )

    db_session.add_all(
        [
            third,
            second,
            first,
        ]
    )
    db_session.flush()

    processed = []

    def fake_process(
        db,
        development,
        current_world_minute,
    ):
        processed.append(
            (
                development.id,
                current_world_minute,
            )
        )

        return development.id in {
            "dev_a",
            "dev_c",
        }

    monkeypatch.setattr(
        development_simulation,
        "process_development",
        fake_process,
    )

    result = development_simulation.tick(
        db_session,
        campaign.id,
        60,
    )

    assert processed == [
        ("dev_a", now),
        ("dev_b", now),
        ("dev_c", now),
    ]

    assert result.changes == 2

def test_construction_advances_when_due(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Construction Progress",
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    construction = WorldDevelopment(
        campaign_id=campaign.id,
        development_type=(
            WorldDevelopmentType.CONSTRUCTION.value
        ),
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Ponte em construção",
        started_world_minute=now,
        next_update_world_minute=now,
        payload_json=(
            '{"progress": 20, '
            '"progress_per_update": 10, '
            '"interval_minutes": 10080}'
        ),
    )

    db_session.add(construction)
    db_session.flush()

    result = development_simulation.tick(
        db_session,
        campaign.id,
        60,
    )
    db_session.flush()
    db_session.refresh(construction)

    payload = json.loads(
        construction.payload_json
    )

    assert result.changes == 1
    assert payload["progress"] == 30
    assert (
        construction.last_updated_world_minute
        == now
    )
    assert (
        construction.next_update_world_minute
        == now + 10080
    )
    assert (
        construction.status
        == WorldDevelopmentStatus.ACTIVE.value
    )

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.actor_id == construction.id,
        )
        .all()
    )

    assert len(events) == 1

    event = events[0]

    assert (
        event.event_type
        == EventType.WORLD_DEVELOPMENT_UPDATED.value
    )
    assert event.world_minute == now

    event_payload = json.loads(event.payload_json)

    assert event_payload["previous_progress"] == 20
    assert event_payload["progress"] == 30


def test_construction_catches_up_missed_updates(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Construction Catch Up",
    )

    start = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    interval = 7 * 24 * 60

    construction = WorldDevelopment(
        campaign_id=campaign.id,
        development_type=(
            WorldDevelopmentType.CONSTRUCTION.value
        ),
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Estrada em construção",
        started_world_minute=start,
        next_update_world_minute=start + interval,
        payload_json=json.dumps(
            {
                "progress": 0,
                "progress_per_update": 10,
                "interval_minutes": interval,
            }
        ),
    )

    db_session.add(construction)
    db_session.flush()

    from app.game.time.clock import advance_world_time

    advance_world_time(
        db_session,
        campaign.id,
        5 * interval,
    )

    result = development_simulation.tick(
        db_session,
        campaign.id,
        5 * interval,
    )
    db_session.flush()
    db_session.refresh(construction)

    payload = json.loads(
        construction.payload_json
    )

    assert result.changes == 1
    assert payload["progress"] == 50
    assert (
        construction.last_updated_world_minute
        == start + 5 * interval
    )
    assert (
        construction.next_update_world_minute
        == start + 6 * interval
    )

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.actor_id == construction.id,
        )
        .order_by(WorldEvent.world_minute.asc())
        .all()
    )

    assert [event.world_minute for event in events] == [
        start + interval,
        start + 2 * interval,
        start + 3 * interval,
        start + 4 * interval,
        start + 5 * interval,
    ]

    assert [
        json.loads(event.payload_json)["progress"]
        for event in events
    ] == [
        10,
        20,
        30,
        40,
        50,
    ]

    assert all(
        event.event_type
        == EventType.WORLD_DEVELOPMENT_UPDATED.value
        for event in events
    )


def test_construction_completes_without_processing_extra_updates(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Construction Completion",
    )

    start = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    interval = 7 * 24 * 60

    construction = WorldDevelopment(
        campaign_id=campaign.id,
        development_type=(
            WorldDevelopmentType.CONSTRUCTION.value
        ),
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Ponte quase pronta",
        started_world_minute=start,
        next_update_world_minute=start + interval,
        payload_json=json.dumps(
            {
                "progress": 80,
                "progress_per_update": 10,
                "interval_minutes": interval,
            }
        ),
    )

    db_session.add(construction)
    db_session.flush()

    from app.game.time.clock import advance_world_time

    advance_world_time(
        db_session,
        campaign.id,
        5 * interval,
    )

    result = development_simulation.tick(
        db_session,
        campaign.id,
        5 * interval,
    )
    db_session.flush()
    db_session.refresh(construction)

    payload = json.loads(
        construction.payload_json
    )

    assert result.changes == 1
    assert payload["progress"] == 100
    assert (
        construction.status
        == WorldDevelopmentStatus.COMPLETED.value
    )
    assert construction.next_update_world_minute is None

    assert (
        construction.last_updated_world_minute
        == start + 2 * interval
    )

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.actor_id == construction.id,
        )
        .order_by(WorldEvent.world_minute.asc())
        .all()
    )

    assert len(events) == 2

    assert [
        event.world_minute
        for event in events
    ] == [
        start + interval,
        start + 2 * interval,
    ]

    assert [
        event.event_type
        for event in events
    ] == [
        EventType.WORLD_DEVELOPMENT_UPDATED.value,
        EventType.WORLD_DEVELOPMENT_COMPLETED.value,
    ]

    assert [
        json.loads(event.payload_json)["progress"]
        for event in events
    ] == [
        90,
        100,
    ]

    development_facts = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.fact_key.in_(
                [
                    f"world_event:{event.id}"
                    for event in events
                ]
            )
        )
        .all()
    )

    facts_by_key = {
        fact.fact_key: fact
        for fact in development_facts
    }

    assert [
        facts_by_key[
            f"world_event:{event.id}"
        ].social_priority
        for event in events
    ] == [
        1,
        3,
    ]

def test_construction_does_not_process_same_update_twice(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Construction Idempotency",
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    interval = 7 * 24 * 60

    construction = WorldDevelopment(
        campaign_id=campaign.id,
        development_type=(
            WorldDevelopmentType.CONSTRUCTION.value
        ),
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Construção idempotente",
        started_world_minute=now,
        next_update_world_minute=now,
        payload_json=json.dumps(
            {
                "progress": 0,
                "progress_per_update": 10,
                "interval_minutes": interval,
            }
        ),
    )

    db_session.add(construction)
    db_session.flush()

    first_result = development_simulation.tick(
        db_session,
        campaign.id,
        60,
    )

    db_session.flush()

    second_result = development_simulation.tick(
        db_session,
        campaign.id,
        60,
    )

    db_session.flush()
    db_session.refresh(construction)

    payload = json.loads(
        construction.payload_json
    )

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.actor_id == construction.id,
        )
        .all()
    )

    assert first_result.changes == 1
    assert second_result.changes == 0

    assert payload["progress"] == 10
    assert len(events) == 1

    assert (
        events[0].event_type
        == EventType.WORLD_DEVELOPMENT_UPDATED.value
    )

    assert events[0].world_minute == now

    assert (
        construction.next_update_world_minute
        == now + interval
    )