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