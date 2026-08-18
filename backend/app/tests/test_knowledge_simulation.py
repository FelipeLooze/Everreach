from app.game.world.seed import create_campaign
from app.db.models.location import Location
from app.simulation import knowledge_simulation
from app.game.time.clock import (
    advance_world_time,
)
from app.core.enums import (
    NPCActivity,
    SimulatedPlayerStatus,
)
from app.db.models.npc import NPC
from app.db.models.simulated_player import (
    SimulatedPlayer,
)
from app.game.character.service import (
    create_character,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)

def test_knowledge_simulation_has_no_opportunity_without_daily_boundary(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Knowledge Cadence Short",
    )

    advance_world_time(
        db_session,
        campaign.id,
        60,
    )

    result = knowledge_simulation.tick(
        db_session,
        campaign.id,
        60,
    )

    assert result.opportunity_world_minutes == ()
    assert result.opportunities == 0
    assert result.propagations == 0
    assert result.resolvable_opportunities == 0


def test_knowledge_simulation_counts_daily_boundaries(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Knowledge Cadence Daily",
    )

    minutes = 24 * 60

    advance_world_time(
        db_session,
        campaign.id,
        minutes,
    )

    result = knowledge_simulation.tick(
        db_session,
        campaign.id,
        minutes,
    )

    assert result.opportunities == 1
    assert result.propagations == 0
    assert (
        result.opportunity_world_minutes
        == (24 * 60,)
    )
    assert result.opportunities == 1
    assert result.resolvable_opportunities == 1


def test_knowledge_simulation_catches_up_multiple_days(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Knowledge Cadence Catch Up",
    )

    minutes = 7 * 24 * 60

    advance_world_time(
        db_session,
        campaign.id,
        minutes,
    )

    result = knowledge_simulation.tick(
        db_session,
        campaign.id,
        minutes,
    )

    assert result.opportunities == 7
    assert result.propagations == 0
    assert (
        result.opportunity_world_minutes
        == (
            1 * 24 * 60,
            2 * 24 * 60,
            3 * 24 * 60,
            4 * 24 * 60,
            5 * 24 * 60,
            6 * 24 * 60,
            7 * 24 * 60,
        )
    )
    assert result.opportunities == 7
    assert (
        result.resolvable_opportunities
        == 1
    )

def test_social_participants_include_only_autonomous_active_people(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Social Participants",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    available_npc = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Available NPC",
        activity=NPCActivity.AVAILABLE.value,
    )

    working_npc = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Working NPC",
        activity=NPCActivity.WORKING.value,
    )

    resting_npc = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Resting NPC",
        activity=NPCActivity.RESTING.value,
    )

    dead_npc = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Dead NPC",
        alive=False,
    )

    active_simulated = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Active Transported",
        location_id=location.id,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )

    dead_simulated = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Dead Transported",
        location_id=location.id,
        status=SimulatedPlayerStatus.DEAD.value,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Player Character",
        region.id,
        location.id,
    )

    db_session.add_all(
        [
            available_npc,
            working_npc,
            resting_npc,
            dead_npc,
            active_simulated,
            dead_simulated,
        ]
    )

    db_session.flush()

    participants = (
        knowledge_simulation
        .eligible_social_participants(
            db_session,
            campaign.id,
        )
    )

    participant_ids = {
        participant.knower_id
        for participant in participants
    }

    assert available_npc.id in participant_ids
    assert working_npc.id in participant_ids
    assert active_simulated.id in participant_ids

    assert resting_npc.id not in participant_ids
    assert dead_npc.id not in participant_ids
    assert dead_simulated.id not in participant_ids

    # O sistema social autônomo nunca decide
    # uma conversa pelo protagonista.
    assert character.id not in participant_ids

def test_social_pairs_only_join_people_at_same_location(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Social Pairs",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    other_location = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.id != location.id,
        )
        .order_by(Location.id)
        .first()
    )

    assert other_location is not None

    first = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="First Social NPC",
        activity=NPCActivity.AVAILABLE.value,
    )

    second = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Second Social Person",
        location_id=location.id,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )

    absent = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Absent Social Person",
        location_id=other_location.id,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )

    db_session.add_all(
        [
            first,
            second,
            absent,
        ]
    )
    db_session.flush()

    pairs = (
        knowledge_simulation
        .eligible_social_pairs(
            db_session,
            campaign.id,
        )
    )

    pair_ids = {
        frozenset(
            (
                pair.first.knower_id,
                pair.second.knower_id,
            )
        )
        for pair in pairs
    }

    assert (
        frozenset(
            (
                first.id,
                second.id,
            )
        )
        in pair_ids
    )

    assert (
        frozenset(
            (
                first.id,
                absent.id,
            )
        )
        not in pair_ids
    )

    assert (
        frozenset(
            (
                second.id,
                absent.id,
            )
        )
        not in pair_ids
    )

    assert all(
        pair.first.knower_id
        != pair.second.knower_id
        for pair in pairs
    )

def test_social_pair_selection_is_deterministic(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Deterministic Social Pair",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    first = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="First",
        activity=NPCActivity.AVAILABLE.value,
    )

    second = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Second",
        activity=NPCActivity.AVAILABLE.value,
    )

    third = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Third",
        location_id=location.id,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )

    db_session.add_all(
        [
            first,
            second,
            third,
        ]
    )
    db_session.flush()

    opportunity_world_minute = (
        24 * 60
    )

    first_selection = (
        knowledge_simulation.select_social_pair(
            db_session,
            campaign.id,
            opportunity_world_minute,
        )
    )

    second_selection = (
        knowledge_simulation.select_social_pair(
            db_session,
            campaign.id,
            opportunity_world_minute,
        )
    )

    assert first_selection is not None
    assert second_selection is not None

    assert (
        first_selection
        == second_selection
    )

    assert (
        first_selection.first.location_id
        == first_selection.second.location_id
    )

    assert (
        first_selection.first.knower_id
        != first_selection.second.knower_id
    )

def test_social_pair_selection_returns_none_without_pair(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "No Social Pair",
    )

    result = (
        knowledge_simulation.select_social_pair(
            db_session,
            campaign.id,
            24 * 60,
        )
    )

    assert result is None