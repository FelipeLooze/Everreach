import json
from app.ai import narrator
from app.ai.context_builder import build_context
from app.game.game_state import build_game_state
from app.db.models.location import Location
from app.simulation import knowledge_simulation
from app.db.models.npc import NPC
from app.game.npcs.service import teach_fact
from app.game.time.clock import (
    advance_world_time,
)
from app.db.models.knowledge import (
    KnowledgeFact,
    KnowledgeKnower,
)
from app.core.enums import (
    EventType,
    KnowledgeCertainty,
    KnowerType,
    NPCActivity,
    SimulatedPlayerStatus,
)
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
from app.db.models.event import WorldEvent


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

def test_social_transfer_candidates_follow_knowledge_difference(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Social Transfer Direction",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    first = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="First Knower",
        activity=NPCActivity.AVAILABLE.value,
    )

    second = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Second Knower",
        location_id=location.id,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )

    db_session.add_all(
        [
            first,
            second,
        ]
    )
    db_session.flush()

    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="social_fact",
        statement="Uma ponte está sendo construída.",
    )

    db_session.add(fact)
    db_session.flush()

    db_session.add(
        KnowledgeKnower(
            fact_id=fact.id,
            knower_type=KnowerType.NPC.value,
            knower_id=first.id,
            source="percepção direta",
            certainty=(
                KnowledgeCertainty.CONFIRMED.value
            ),
        )
    )

    db_session.flush()

    pair = knowledge_simulation.SocialPair(
        first=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=first.id,
            location_id=location.id,
        ),
        second=knowledge_simulation.SocialParticipant(
            knower_type=(
                KnowerType.SIMULATED_PLAYER
            ),
            knower_id=second.id,
            location_id=location.id,
        ),
    )

    candidates = (
        knowledge_simulation
        .eligible_transfer_candidates(
            db_session,
            campaign.id,
            pair,
        )
    )

    assert len(candidates) == 1

    candidate = candidates[0]

    assert candidate.source.knower_id == first.id
    assert candidate.target.knower_id == second.id
    assert candidate.fact_key == fact.fact_key
    assert candidate.social_priority == 1

def test_secret_fact_is_not_eligible_for_automatic_social_transfer(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Secret Social Knowledge",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    first = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Secret Knower",
        activity=NPCActivity.AVAILABLE.value,
    )

    second = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Unaware NPC",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            first,
            second,
        ]
    )
    db_session.flush()

    secret = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="secret_fact",
        statement="Existe uma passagem escondida.",
        is_secret=True,
    )

    db_session.add(secret)
    db_session.flush()

    db_session.add(
        KnowledgeKnower(
            fact_id=secret.id,
            knower_type=KnowerType.NPC.value,
            knower_id=first.id,
        )
    )

    db_session.flush()

    pair = knowledge_simulation.SocialPair(
        first=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=first.id,
            location_id=location.id,
        ),
        second=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=second.id,
            location_id=location.id,
        ),
    )

    candidates = (
        knowledge_simulation
        .eligible_transfer_candidates(
            db_session,
            campaign.id,
            pair,
        )
    )

    assert candidates == ()

def test_social_transfer_candidate_selection_is_deterministic(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Deterministic Transfer Candidate",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    first = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    second = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Target",
        location_id=location.id,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )

    db_session.add_all(
        [
            first,
            second,
        ]
    )
    db_session.flush()

    facts = [
        KnowledgeFact(
            campaign_id=campaign.id,
            fact_key="social_fact_a",
            statement="Fato A.",
        ),
        KnowledgeFact(
            campaign_id=campaign.id,
            fact_key="social_fact_b",
            statement="Fato B.",
        ),
    ]

    db_session.add_all(facts)
    db_session.flush()

    for fact in facts:
        db_session.add(
            KnowledgeKnower(
                fact_id=fact.id,
                knower_type=KnowerType.NPC.value,
                knower_id=first.id,
                source="percepção direta",
                certainty=(
                    KnowledgeCertainty.CONFIRMED.value
                ),
            )
        )

    db_session.flush()

    pair = knowledge_simulation.SocialPair(
        first=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=first.id,
            location_id=location.id,
        ),
        second=knowledge_simulation.SocialParticipant(
            knower_type=(
                KnowerType.SIMULATED_PLAYER
            ),
            knower_id=second.id,
            location_id=location.id,
        ),
    )

    opportunity_world_minute = 24 * 60

    first_selection = (
        knowledge_simulation
        .select_transfer_candidate(
            db_session,
            campaign.id,
            pair,
            opportunity_world_minute,
        )
    )

    second_selection = (
        knowledge_simulation
        .select_transfer_candidate(
            db_session,
            campaign.id,
            pair,
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
        first_selection.fact_key
        in {
            "social_fact_a",
            "social_fact_b",
        }
    )

    assert (
        first_selection.source.knower_id
        == first.id
    )

    assert (
        first_selection.target.knower_id
        == second.id
    )

def test_social_transfer_candidate_selection_returns_none_without_candidates(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "No Transfer Candidate",
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

    db_session.add_all(
        [
            first,
            second,
        ]
    )
    db_session.flush()

    pair = knowledge_simulation.SocialPair(
        first=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=first.id,
            location_id=location.id,
        ),
        second=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=second.id,
            location_id=location.id,
        ),
    )

    result = (
        knowledge_simulation
        .select_transfer_candidate(
            db_session,
            campaign.id,
            pair,
            24 * 60,
        )
    )

    assert result is None

def test_social_opportunity_automatically_propagates_one_fact(
    db_session,
    fake_llm,
):
    campaign = create_campaign(
        db_session,
        "Automatic Social Propagation",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    # Remove participantes autônomos do seed
    # para controlar exatamente o par do teste.
    db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id
    ).update(
        {
            NPC.activity:
            NPCActivity.RESTING.value
        },
        synchronize_session=False,
    )

    db_session.query(SimulatedPlayer).filter(
        SimulatedPlayer.campaign_id
        == campaign.id
    ).update(
        {
            SimulatedPlayer.status:
            SimulatedPlayerStatus.DEAD.value
        },
        synchronize_session=False,
    )

    source = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    target = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Target",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="automatic_social_fact",
        statement="Uma nova ponte está sendo construída.",
    )

    db_session.add(fact)
    db_session.flush()

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        source.id,
        source="percepção direta",
        certainty=KnowledgeCertainty.CONFIRMED,
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
    assert result.resolvable_opportunities == 1
    assert result.propagations == 1

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .count()
        == 1
    )

    target_link = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id
            == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .one()
    )

    assert (
        target_link.certainty
        == KnowledgeCertainty.BELIEVED.value
    )

    propagation_event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign.id,
            WorldEvent.event_type
            == EventType.KNOWLEDGE_PROPAGATED.value,
        )
        .one()
    )

    payload = json.loads(
        propagation_event.payload_json
    )

    assert (
        payload["source_certainty"]
        == KnowledgeCertainty.CONFIRMED.value
    )

    assert (
        payload["target_certainty"]
        == KnowledgeCertainty.BELIEVED.value
    )

    character = create_character(
        db_session,
        campaign.id,
        "Player Character",
        region.id,
        location.id,
    )

    db_session.flush()

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    player_input = "O que voce sabe sobre a ponte?"

    context = build_context(
        db_session,
        state,
        active_interlocutor="Target",
        player_input=player_input,
    )

    npc_section = (
        context
        .split("NPC KNOWLEDGE", 1)[1]
        .split("PLAYER KNOWLEDGE", 1)[0]
    )

    assert fact.statement in npc_section

    fact_line = next(
        line
        for line in npc_section.splitlines()
        if fact.statement in line
    )

    assert "[BELIEVED; fonte:" in fact_line
    assert "[CONFIRMED; fonte:" not in fact_line

    narrator.narrate(
        fake_llm,
        "Nenhuma mudanca mecanica.",
        context,
        player_input,
        "",
    )

    _narrator_system, narrator_prompt = fake_llm.calls[-1]

    assert fact.statement in narrator_prompt
    assert fact_line.strip() in narrator_prompt

def test_social_believed_fact_becomes_rumor_in_narrator_context(
    db_session,
    fake_llm,
):
    campaign = create_campaign(
        db_session,
        "Social Rumor Propagation",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id
    ).update(
        {
            NPC.activity:
            NPCActivity.RESTING.value
        },
        synchronize_session=False,
    )

    db_session.query(SimulatedPlayer).filter(
        SimulatedPlayer.campaign_id
        == campaign.id
    ).update(
        {
            SimulatedPlayer.status:
            SimulatedPlayerStatus.DEAD.value
        },
        synchronize_session=False,
    )

    source = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Rumor Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    target = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Rumor Target",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="social_believed_to_rumor",
        statement="A estrada do leste esta alagada.",
    )

    db_session.add(fact)
    db_session.flush()

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        source.id,
        source="relato confiavel",
        certainty=KnowledgeCertainty.BELIEVED,
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
    assert result.resolvable_opportunities == 1
    assert result.propagations == 1

    target_link = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .one()
    )

    assert (
        target_link.certainty
        == KnowledgeCertainty.RUMOR.value
    )

    propagation_event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign.id,
            WorldEvent.event_type
            == EventType.KNOWLEDGE_PROPAGATED.value,
        )
        .one()
    )

    payload = json.loads(
        propagation_event.payload_json
    )

    assert (
        payload["source_certainty"]
        == KnowledgeCertainty.BELIEVED.value
    )

    assert (
        payload["target_certainty"]
        == KnowledgeCertainty.RUMOR.value
    )

    character = create_character(
        db_session,
        campaign.id,
        "Player Character",
        region.id,
        location.id,
    )

    db_session.flush()

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    player_input = "O que voce sabe sobre a estrada do leste?"

    context = build_context(
        db_session,
        state,
        active_interlocutor="Rumor Target",
        player_input=player_input,
    )

    npc_section = (
        context
        .split("NPC KNOWLEDGE", 1)[1]
        .split("PLAYER KNOWLEDGE", 1)[0]
    )

    assert fact.statement in npc_section

    fact_line = next(
        line
        for line in npc_section.splitlines()
        if fact.statement in line
    )

    assert "[RUMOR; fonte:" in fact_line
    assert "[BELIEVED; fonte:" not in fact_line
    assert "[CONFIRMED; fonte:" not in fact_line

    narrator.narrate(
        fake_llm,
        "Nenhuma mudanca mecanica.",
        context,
        player_input,
        "",
    )

    _narrator_system, narrator_prompt = fake_llm.calls[-1]

    assert fact.statement in narrator_prompt
    assert fact_line.strip() in narrator_prompt

def test_same_social_opportunity_is_not_resolved_twice(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Social Opportunity Idempotency",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id
    ).update(
        {
            NPC.activity:
            NPCActivity.RESTING.value
        },
        synchronize_session=False,
    )

    db_session.query(SimulatedPlayer).filter(
        SimulatedPlayer.campaign_id
        == campaign.id
    ).update(
        {
            SimulatedPlayer.status:
            SimulatedPlayerStatus.DEAD.value
        },
        synchronize_session=False,
    )

    source = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    target = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Target",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    facts = [
        KnowledgeFact(
            campaign_id=campaign.id,
            fact_key="social_idempotent_a",
            statement="Fato A.",
        ),
        KnowledgeFact(
            campaign_id=campaign.id,
            fact_key="social_idempotent_b",
            statement="Fato B.",
        ),
    ]

    db_session.add_all(facts)
    db_session.flush()

    for fact in facts:
        teach_fact(
            db_session,
            campaign.id,
            fact.fact_key,
            KnowerType.NPC,
            source.id,
        )

    minutes = 24 * 60

    advance_world_time(
        db_session,
        campaign.id,
        minutes,
    )

    first_result = knowledge_simulation.tick(
        db_session,
        campaign.id,
        minutes,
    )

    second_result = knowledge_simulation.tick(
        db_session,
        campaign.id,
        minutes,
    )

    assert first_result.propagations == 1
    assert second_result.propagations == 0

    learned_count = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id.in_(
                [fact.id for fact in facts]
            ),
            KnowledgeKnower.knower_id
            == target.id,
        )
        .count()
    )

    assert learned_count == 1

    resolved_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType
            .SOCIAL_KNOWLEDGE_OPPORTUNITY_RESOLVED
            .value,
        )
        .count()
    )

    assert resolved_events == 1

def test_social_catch_up_propagates_at_most_one_fact(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Social Catch Up Limit",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    # Remove participantes autônomos do seed
    # para controlar exatamente o par.
    db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id
    ).update(
        {
            NPC.activity:
            NPCActivity.RESTING.value
        },
        synchronize_session=False,
    )

    db_session.query(SimulatedPlayer).filter(
        SimulatedPlayer.campaign_id
        == campaign.id
    ).update(
        {
            SimulatedPlayer.status:
            SimulatedPlayerStatus.DEAD.value
        },
        synchronize_session=False,
    )

    source = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Catch Up Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    target = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Catch Up Target",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    facts = [
        KnowledgeFact(
            campaign_id=campaign.id,
            fact_key="catch_up_fact_a",
            statement="Fato A.",
        ),
        KnowledgeFact(
            campaign_id=campaign.id,
            fact_key="catch_up_fact_b",
            statement="Fato B.",
        ),
        KnowledgeFact(
            campaign_id=campaign.id,
            fact_key="catch_up_fact_c",
            statement="Fato C.",
        ),
    ]

    db_session.add_all(facts)
    db_session.flush()

    for fact in facts:
        teach_fact(
            db_session,
            campaign.id,
            fact.fact_key,
            KnowerType.NPC,
            source.id,
            source="percepção direta",
            certainty=KnowledgeCertainty.CONFIRMED,
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
    assert result.resolvable_opportunities == 1
    assert result.propagations == 1

    learned_count = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id.in_(
                [
                    fact.id
                    for fact in facts
                ]
            ),
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .count()
    )

    assert learned_count == 1

    propagated_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.KNOWLEDGE_PROPAGATED.value,
        )
        .count()
    )

    assert propagated_events == 1

    resolved_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType
            .SOCIAL_KNOWLEDGE_OPPORTUNITY_RESOLVED
            .value,
        )
        .count()
    )

    assert resolved_events == 1

def test_zero_priority_fact_is_not_eligible_for_social_transfer(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Zero Priority Knowledge",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    source = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    target = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Target",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="zero_priority_fact",
        statement="Informação pública, mas não social.",
        social_priority=0,
    )

    db_session.add(fact)
    db_session.flush()

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        source.id,
        source="percepção direta",
        certainty=KnowledgeCertainty.CONFIRMED,
    )

    pair = knowledge_simulation.SocialPair(
        first=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=source.id,
            location_id=location.id,
        ),
        second=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=target.id,
            location_id=location.id,
        ),
    )

    candidates = (
        knowledge_simulation
        .eligible_transfer_candidates(
            db_session,
            campaign.id,
            pair,
        )
    )

    assert all(
        candidate.fact_key
        != fact.fact_key
        for candidate in candidates
    )

def test_social_transfer_selection_uses_social_priority_weight(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Weighted Social Selection",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    source = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Weighted Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    target = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Weighted Target",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    low_priority = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="priority_a",
        statement="Assunto comum.",
        social_priority=1,
    )

    high_priority = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="priority_b",
        statement="Assunto muito importante.",
        social_priority=3,
    )

    db_session.add_all(
        [
            low_priority,
            high_priority,
        ]
    )
    db_session.flush()

    for fact in (
        low_priority,
        high_priority,
    ):
        teach_fact(
            db_session,
            campaign.id,
            fact.fact_key,
            KnowerType.NPC,
            source.id,
            source="percepção direta",
            certainty=KnowledgeCertainty.CONFIRMED,
        )

    teach_fact(
            db_session,
            campaign.id,
            high_priority.fact_key,
            KnowerType.NPC,
            target.id,
            source="boato anterior",
            certainty=KnowledgeCertainty.RUMOR,
        )

    pair = knowledge_simulation.SocialPair(
        first=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=source.id,
            location_id=location.id,
        ),
        second=knowledge_simulation.SocialParticipant(
            knower_type=KnowerType.NPC,
            knower_id=target.id,
            location_id=location.id,
        ),
    )

    class FakeHash:
        def digest(self):
            return (
                (2).to_bytes(
                    8,
                    byteorder="big",
                    signed=False,
                )
                + bytes(24)
            )

    monkeypatch.setattr(
        knowledge_simulation.hashlib,
        "sha256",
        lambda value: FakeHash(),
    )

    selected = (
        knowledge_simulation
        .select_transfer_candidate(
            db_session,
            campaign.id,
            pair,
            24 * 60,
        )
    )

    assert selected is not None
    assert selected.fact_key == "priority_b"
    assert selected.social_priority == 3

def test_social_transfer_certainty_degrades_hearsay():
    assert (
        knowledge_simulation
        .social_transfer_certainty(
            KnowledgeCertainty.CONFIRMED
        )
        == KnowledgeCertainty.BELIEVED
    )

    assert (
        knowledge_simulation
        .social_transfer_certainty(
            KnowledgeCertainty.BELIEVED
        )
        == KnowledgeCertainty.RUMOR
    )

    assert (
        knowledge_simulation
        .social_transfer_certainty(
            KnowledgeCertainty.RUMOR
        )
        == KnowledgeCertainty.RUMOR
    )

def test_social_opportunity_propagates_fact_to_simulated_player(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "NPC To Simulated Player Propagation",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    # Remove participantes autônomos do seed
    # para controlar exatamente o par do teste.
    db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id
    ).update(
        {
            NPC.activity:
            NPCActivity.RESTING.value
        },
        synchronize_session=False,
    )

    db_session.query(SimulatedPlayer).filter(
        SimulatedPlayer.campaign_id
        == campaign.id
    ).update(
        {
            SimulatedPlayer.status:
            SimulatedPlayerStatus.DEAD.value
        },
        synchronize_session=False,
    )

    source = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="NPC Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    target = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Transported Target",
        location_id=location.id,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="npc_to_simulated_social_fact",
        statement="Mercadores chegaram pela estrada do sul.",
    )

    db_session.add(fact)
    db_session.flush()

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        source.id,
        source="percepcao direta",
        certainty=KnowledgeCertainty.CONFIRMED,
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
    assert result.resolvable_opportunities == 1
    assert result.propagations == 1

    target_link = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.SIMULATED_PLAYER.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .one()
    )

    assert (
        target_link.certainty
        == KnowledgeCertainty.BELIEVED.value
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.SIMULATED_PLAYER.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .count()
        == 1
    )

def test_social_opportunity_propagates_fact_from_simulated_player_to_npc(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Simulated Player To NPC Propagation",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    # Remove participantes autônomos do seed
    # para controlar exatamente o par do teste.
    db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id
    ).update(
        {
            NPC.activity:
            NPCActivity.RESTING.value
        },
        synchronize_session=False,
    )

    db_session.query(SimulatedPlayer).filter(
        SimulatedPlayer.campaign_id
        == campaign.id
    ).update(
        {
            SimulatedPlayer.status:
            SimulatedPlayerStatus.DEAD.value
        },
        synchronize_session=False,
    )

    source = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Transported Source",
        location_id=location.id,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )

    target = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="NPC Target",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="simulated_to_npc_social_fact",
        statement="Um grupo de viajantes cruzou o vale.",
    )

    db_session.add(fact)
    db_session.flush()

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.SIMULATED_PLAYER,
        source.id,
        source="percepcao direta",
        certainty=KnowledgeCertainty.CONFIRMED,
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
    assert result.resolvable_opportunities == 1
    assert result.propagations == 1

    target_link = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .one()
    )

    assert (
        target_link.certainty
        == KnowledgeCertainty.BELIEVED.value
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .count()
        == 1
    )

def test_social_opportunity_upgrades_weaker_existing_certainty(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Social Certainty Upgrade",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id
    ).update(
        {
            NPC.activity:
            NPCActivity.RESTING.value
        },
        synchronize_session=False,
    )

    db_session.query(SimulatedPlayer).filter(
        SimulatedPlayer.campaign_id
        == campaign.id
    ).update(
        {
            SimulatedPlayer.status:
            SimulatedPlayerStatus.DEAD.value
        },
        synchronize_session=False,
    )

    source = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Confirmed Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    target = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Rumor Target",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="social_certainty_upgrade",
        statement="A ponte do norte foi destruida.",
    )

    db_session.add(fact)
    db_session.flush()

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        source.id,
        source="percepcao direta",
        certainty=KnowledgeCertainty.CONFIRMED,
    )

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        target.id,
        source="boato antigo",
        certainty=KnowledgeCertainty.RUMOR,
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
    assert result.resolvable_opportunities == 1
    assert result.propagations == 1

    target_link = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .one()
    )

    assert (
        target_link.certainty
        == KnowledgeCertainty.BELIEVED.value
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .count()
        == 1
    )

def test_social_opportunity_does_not_repeat_fact_without_certainty_improvement(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Social Certainty No Improvement",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id
    ).update(
        {
            NPC.activity:
            NPCActivity.RESTING.value
        },
        synchronize_session=False,
    )

    db_session.query(SimulatedPlayer).filter(
        SimulatedPlayer.campaign_id
        == campaign.id
    ).update(
        {
            SimulatedPlayer.status:
            SimulatedPlayerStatus.DEAD.value
        },
        synchronize_session=False,
    )

    source = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Confirmed Source",
        activity=NPCActivity.AVAILABLE.value,
    )

    target = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Believed Target",
        activity=NPCActivity.AVAILABLE.value,
    )

    db_session.add_all(
        [
            source,
            target,
        ]
    )
    db_session.flush()

    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="social_certainty_no_improvement",
        statement="A ponte do norte foi destruida.",
    )

    db_session.add(fact)
    db_session.flush()

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        source.id,
        source="percepcao direta",
        certainty=KnowledgeCertainty.CONFIRMED,
    )

    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        target.id,
        source="relato confiavel",
        certainty=KnowledgeCertainty.BELIEVED,
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
    assert result.resolvable_opportunities == 1
    assert result.propagations == 0

    target_link = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .one()
    )

    assert (
        target_link.certainty
        == KnowledgeCertainty.BELIEVED.value
    )

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == KnowerType.NPC.value,
            KnowledgeKnower.knower_id
            == target.id,
        )
        .count()
        == 1
    )