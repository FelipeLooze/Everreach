from app.core.enums import RiskTolerance
from app.db.models.location import LocationConnection
from app.db.models.simulated_player import SimulatedPlayer


RISK_LIMITS = {
    RiskTolerance.CAUTIOUS.value: 1,
    RiskTolerance.BALANCED.value: 3,
    RiskTolerance.BOLD.value: 5,
}


def acceptable_connections(
    player: SimulatedPlayer,
    connections: list[LocationConnection],
) -> list[LocationConnection]:
    limit = RISK_LIMITS.get(getattr(player, "risk_tolerance", "BALANCED"), 3)
    return [
        connection
        for connection in connections
        if getattr(connection, "danger", 0) <= limit
    ]
