from app.core.enums import SimulatedPlayerActivity
from app.ai.llm_service import LLMService
from app.game.game_state import build_game_state
from app.game.character.service import create_character
from app.game.relationships.service import (
    record_simulated_player_interaction,
)
from app.game.players.service import (
    meet_simulated_player,
    select_existing_simulated_player_for_encounter,
    select_known_simulated_player_for_reencounter,
    simulated_players_at_location,
    get_active_simulated_player_interlocutor,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)
from app.game.players.encounter import (
    resolve_simulated_player_encounter,
)

class _FailIfCalledLLM(LLMService):
    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self,
        system: str,
        prompt: str,
    ) -> str:
        self.calls += 1
        raise AssertionError(
            "LLM must not be called when a persistent "
            "person can resolve the encounter."
        )


class _ChooseLast:
    def choice(self, candidates):
        return candidates[-1]

class _ChooseMostFrequent:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def choice(self, candidates):
        for candidate in candidates:
            self.counts[candidate.id] = (
                self.counts.get(
                    candidate.id,
                    0,
                )
                + 1
            )

        return max(
            candidates,
            key=lambda candidate: self.counts[
                candidate.id
            ],
        )

def test_known_present_transportee_can_be_selected_for_reencounter(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Natural Reencounter",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert len(players) >= 2

    known_player = players[0]
    unknown_player = players[1]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        known_player.id,
    )

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is not None
    assert selected.id == known_player.id
    assert selected.id != unknown_player.id


def test_relationship_biases_plausible_reencounter_without_excluding_anyone(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Relationship Reencounter Bias",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert len(players) >= 2

    disliked_player = players[0]
    liked_player = players[1]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        disliked_player.id,
    )

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        liked_player.id,
    )

    record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        disliked_player.id,
        trust_delta=-60,
        affinity_delta=-60,
    )

    record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        liked_player.id,
        trust_delta=60,
        affinity_delta=60,
    )

    chooser = _ChooseMostFrequent()

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
            rng=chooser,
        )
    )

    assert selected is not None
    assert selected.id == liked_player.id

    assert (
        chooser.counts[liked_player.id]
        > chooser.counts[disliked_player.id]
    )

    assert chooser.counts[disliked_player.id] > 0

    assert (
        disliked_player.location_id
        == location.id
    )
    assert (
        liked_player.location_id
        == location.id
    )


def test_known_transportee_in_transit_cannot_be_reencountered(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Blocks Reencounter",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    player.travel_arrival_world_minute = 999999

    db_session.flush()

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is None

def test_unknown_present_transportee_is_not_a_reencounter(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Unknown Person Is Not Reencounter",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert players

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is None

def test_resting_known_transportee_is_not_available_for_reencounter(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Resting Reencounter",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    player.activity = (
        SimulatedPlayerActivity.RESTING.value
    )

    db_session.flush()

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is None

def test_working_known_transportee_can_be_reencountered(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Working Reencounter",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    player.activity = (
        SimulatedPlayerActivity.WORKING.value
    )

    db_session.flush()

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is not None
    assert selected.id == player.id

def test_training_known_transportee_can_be_reencountered(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Training Reencounter",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    player.activity = (
        SimulatedPlayerActivity.TRAINING.value
    )

    db_session.flush()

    selected = (
        select_known_simulated_player_for_reencounter(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert selected is not None
    assert selected.id == player.id

def test_resting_transportees_are_not_selected_for_casual_encounter(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Resting Casual Encounter",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert players

    for player in players:
        player.activity = (
            SimulatedPlayerActivity.RESTING.value
        )

    db_session.flush()

    selected = (
        select_existing_simulated_player_for_encounter(
            db_session,
            campaign.id,
            location.id,
        )
    )

    assert selected is None

def test_encounter_resolver_prioritizes_known_present_transportee(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Resolver Reencounter Priority",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert len(players) >= 2

    known_player = players[0]
    other_player = players[-1]

    assert known_player.id != other_player.id

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        known_player.id,
    )

    llm = _FailIfCalledLLM()

    resolved = resolve_simulated_player_encounter(
        db_session,
        llm,
        campaign.id,
        location.id,
        rng=_ChooseLast(),
        character_id=character.id,
    )

    assert resolved is not None
    assert resolved.id == known_player.id
    assert llm.calls == 0

def test_encounter_resolver_falls_back_to_unknown_persistent_transportee(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Resolver Persistent Fallback",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert players

    expected = players[-1]

    llm = _FailIfCalledLLM()

    resolved = resolve_simulated_player_encounter(
        db_session,
        llm,
        campaign.id,
        location.id,
        rng=_ChooseLast(),
        character_id=character.id,
    )

    assert resolved is not None
    assert resolved.id == expected.id
    assert llm.calls == 0

def test_resting_transportee_is_not_nearby_in_real_game_state(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Resting Transportee Game State",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    player.activity = (
        SimulatedPlayerActivity.RESTING.value
    )

    db_session.flush()

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    nearby_ids = {
        nearby.id
        for nearby in state.nearby_simulated_players
    }

    assert player.id not in nearby_ids

    # Physical presence itself was not erased.
    physical_ids = {
        nearby.id
        for nearby in simulated_players_at_location(
            db_session,
            location.id,
        )
    }

    assert player.id in physical_ids

def test_working_transportee_remains_nearby_in_real_game_state(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Working Transportee Game State",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    player.activity = (
        SimulatedPlayerActivity.WORKING.value
    )

    db_session.flush()

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    nearby_ids = {
        nearby.id
        for nearby in state.nearby_simulated_players
    }

    assert player.id in nearby_ids

def test_resting_transportee_is_no_longer_active_interlocutor(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Resting Active Interlocutor",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    assert (
        get_active_simulated_player_interlocutor(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
        is player
    )

    player.activity = (
        SimulatedPlayerActivity.RESTING.value
    )

    db_session.flush()

    assert (
        get_active_simulated_player_interlocutor(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
        is None
    )