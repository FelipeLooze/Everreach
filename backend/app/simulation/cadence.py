def boundaries_crossed(
    end_total_minutes: int,
    elapsed_minutes: int,
    interval_minutes: int,
) -> int:
    if elapsed_minutes <= 0:
        return 0

    if interval_minutes <= 0:
        raise ValueError(
            "interval_minutes must be greater than zero"
        )

    start_total_minutes = (
        end_total_minutes - elapsed_minutes
    )

    return (
        end_total_minutes // interval_minutes
        - start_total_minutes // interval_minutes
    )

def boundary_minutes_crossed(
    end_total_minutes: int,
    elapsed_minutes: int,
    interval_minutes: int,
) -> tuple[int, ...]:
    if elapsed_minutes <= 0:
        return ()

    if interval_minutes <= 0:
        raise ValueError(
            "interval_minutes must be greater than zero"
        )

    start_total_minutes = (
        end_total_minutes - elapsed_minutes
    )

    first_boundary = (
        (
            start_total_minutes
            // interval_minutes
        )
        + 1
    ) * interval_minutes

    if first_boundary > end_total_minutes:
        return ()

    return tuple(
        range(
            first_boundary,
            end_total_minutes + 1,
            interval_minutes,
        )
    )

def scheduled_occurrences_due(
    current_world_minute: int,
    next_update_world_minute: int | None,
    interval_minutes: int,
) -> int:
    if interval_minutes <= 0:
        raise ValueError(
            "interval_minutes must be greater than zero"
        )

    if next_update_world_minute is None:
        return 0

    if next_update_world_minute > current_world_minute:
        return 0

    return (
        1
        + (
            current_world_minute
            - next_update_world_minute
        )
        // interval_minutes
    )