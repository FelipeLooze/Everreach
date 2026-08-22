"""Phase 17L — Discovery Events.

Discovery events already exist and already fire from real discoveries —
LOCATION_DISCOVERED/CONNECTION_DISCOVERED (Phase 1, reused by 17D's
explore_current_location and 17I's expeditions), EXPLORATION_ATTEMPTED
(17D), NAVIGATION_HAZARD_ENCOUNTERED (17K). Nothing new needed there;
this module only adds what those events were missing: a significance
tier attached to the discovery, so a future consumer (17Q, owned by
Phase 8 — this module grants no XP itself) can tell "found an entire
settlement" apart from "found a game trail" without inventing a whole
scoring system.

"Avoid farming discovery by repeatedly walking slightly farther into
identical terrain" (spec) is already structurally impossible with the
existing design, not something this module needs to defend against:
CharacterConnectionDiscovery rows are create-once (app.game.discovery.service),
so app.game.exploration.service.explore_current_location's own
candidate pool for one location strictly shrinks and eventually empties
— searching the same spot twice cannot double-reward the same
connection.
"""

from app.core.enums import DiscoverySignificance
from app.db.models.location import Location

_MAJOR_SETTLEMENT_TYPES = {"village", "town", "city", "major_city"}
_NON_NOTABLE_TYPES = {"interior", "district"}


def assess_location_discovery_significance(location: Location) -> DiscoverySignificance:
    if location.type in _MAJOR_SETTLEMENT_TYPES or location.type == "region_frontier":
        return DiscoverySignificance.MAJOR
    if location.materialization_tier in (1, 2) and location.type not in _NON_NOTABLE_TYPES:
        return DiscoverySignificance.NOTABLE
    return DiscoverySignificance.MINOR
