from app.db.models.simulated_player import (
    SimulatedPlayerPopulation,
)
from app.game.players.service import (
    abstract_simulated_player_count_at_location,
    set_abstract_simulated_player_population,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)


def test_abstract_transported_population_is_persistent_and_explicit(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Abstract Population",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 0
    )

    population = (
        set_abstract_simulated_player_population(
            db_session,
            campaign.id,
            location.id,
            7,
        )
    )

    assert population.abstract_count == 7

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 7
    )

    rows = (
        db_session.query(
            SimulatedPlayerPopulation
        )
        .filter(
            SimulatedPlayerPopulation.location_id
            == location.id
        )
        .all()
    )

    assert len(rows) == 1