from app.core.enums import NPCActivity


def activity_for_role(
    role: str,
    hour: int,
) -> NPCActivity:
    normalized_role = role.strip().casefold()

    if hour >= 22 or hour < 6:
        return NPCActivity.RESTING

    if normalized_role in {
        "ferreiro",
        "estalajadeiro",
    }:
        if 8 <= hour < 18:
            return NPCActivity.WORKING

    return NPCActivity.AVAILABLE
