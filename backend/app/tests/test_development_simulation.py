from app.simulation import development_simulation


def test_development_simulation_currently_makes_no_changes(
    db_session,
):
    result = development_simulation.tick(
        db_session,
        "campaign_test",
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