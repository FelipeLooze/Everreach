import random

from app.game.players.service import (
    select_existing_simulated_player_for_encounter,
    simulated_players_at_location,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)


def test_encounter_reuses_existing_transported_person(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Existing Encounter",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    before = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert before

    before_ids = {
        player.id
        for player in before
    }

    selected = (
        select_existing_simulated_player_for_encounter(
            db_session,
            campaign.id,
            location.id,
            rng=random.Random(42),
        )
    )

    after = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert selected is not None
    assert selected.id in before_ids

    assert {
        player.id
        for player in after
    } == before_ids