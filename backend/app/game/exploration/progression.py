"""Phase 17Q — Exploration Progression Integration.

"Phase 17 itself does not decide those rewards" (spec) is taken
literally: nothing in 17D/17I/17K/17L calls anything here automatically
— none of them award evidence on their own. This module is the
optional bridge a caller (ultimately Phase 8's own progression wiring)
invokes when it decides an exploration outcome deserves evidence.

signal_for_* functions are pure — they read an already-resolved
outcome (ExplorationOutcome from 17D, an Expedition from 17I, a Map
from 17G) and describe what evidence it *could* produce, never
touching the database. apply_exploration_progression_signal is the one
function that actually calls app.game.domains.service.award_domain_evidence
(Phase 8, reused wholesale — no parallel progression system).

A real, pre-existing gap this module does NOT try to fix: no
production code anywhere in Everreach seeds DomainDefinition rows
(confirmed by exhaustive search — every DomainDefinition("SWORD"/"WIND"/
...) in the repository exists only in test fixtures). Domain evidence
can only ever be awarded for a domain that already exists in this
campaign's catalog, and establishing that catalog is Phase 8's own
responsibility, not something Phase 17 should reach into and solve as
a side effect. apply_exploration_progression_signal therefore no-ops
(returns None) rather than raising when the target domain doesn't
exist yet — evidence is lost, not crashed, exactly as it would be for
any other Phase 8 caller today.

CARTOGRAPHY PROFESSION (spec): signal_for_cartography only ever fires
from an actual create_map call (17G) — real cartographic work, never
from merely owning or buying a map. EXPLORER DOES NOT NEED TO BE A
CLASS: nothing here touches ClassDefinition/Profession at all, only
Domain evidence — Phase 8's own class-emergence machinery (not this
module) is what would eventually let a class emerge from a real
pattern of domain evidence, if it ever does.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import DiscoverySignificance, DomainEvidenceSource, ExpeditionStatus
from app.db.models.character import Character
from app.db.models.domain import DomainDefinition
from app.db.models.expedition import Expedition
from app.db.models.map import Map
from app.game.domains.service import DomainEvidenceAward, award_domain_evidence
from app.game.exploration.service import ExplorationOutcome

_DISCOVERY_AMOUNT_BY_SIGNIFICANCE = {
    DiscoverySignificance.MINOR: 1.0,
    DiscoverySignificance.NOTABLE: 2.5,
    DiscoverySignificance.MAJOR: 5.0,
}
_EXPEDITION_AMOUNT_BY_STATUS = {
    ExpeditionStatus.SUCCEEDED: 5.0,
    ExpeditionStatus.PARTIAL_SUCCESS: 2.0,
}
CARTOGRAPHY_MAP_CREATED_AMOUNT = 2.0


@dataclass
class ExplorationProgressionSignal:
    domain_key: str
    source: DomainEvidenceSource
    evidence_key: str
    context_key: str
    amount: float


def signal_for_successful_exploration(outcome: ExplorationOutcome) -> ExplorationProgressionSignal | None:
    if not outcome.success or outcome.significance is None or outcome.found_location_id is None:
        return None
    source = (
        DomainEvidenceSource.ACHIEVEMENT
        if outcome.significance == DiscoverySignificance.MAJOR
        else DomainEvidenceSource.EXPERIENCE
    )
    return ExplorationProgressionSignal(
        domain_key="SURVEY",
        source=source,
        evidence_key="location_discovered",
        context_key=outcome.found_location_id,
        amount=_DISCOVERY_AMOUNT_BY_SIGNIFICANCE[outcome.significance],
    )


def signal_for_expedition(expedition: Expedition) -> ExplorationProgressionSignal | None:
    status = ExpeditionStatus(expedition.status)
    amount = _EXPEDITION_AMOUNT_BY_STATUS.get(status)
    if amount is None:
        return None
    return ExplorationProgressionSignal(
        domain_key="EXPEDITION",
        source=DomainEvidenceSource.ACHIEVEMENT,
        evidence_key="expedition_resolved",
        context_key=expedition.id,
        amount=amount,
    )


def signal_for_cartography(map_row: Map) -> ExplorationProgressionSignal:
    return ExplorationProgressionSignal(
        domain_key="CARTOGRAPHY",
        source=DomainEvidenceSource.EXPERIENCE,
        evidence_key="map_created",
        context_key=map_row.id,
        amount=CARTOGRAPHY_MAP_CREATED_AMOUNT,
    )


def apply_exploration_progression_signal(
    db: Session,
    campaign_id: str,
    character: Character,
    signal: ExplorationProgressionSignal,
) -> DomainEvidenceAward | None:
    """None means the target domain doesn't exist in this campaign's
    catalog yet — a real, pre-existing Phase 8 gap this module does not
    attempt to paper over (see module docstring)."""
    if db.get(DomainDefinition, signal.domain_key) is None:
        return None
    return award_domain_evidence(
        db, campaign_id, character,
        domain_key=signal.domain_key,
        source=signal.source,
        evidence_key=signal.evidence_key,
        context_key=signal.context_key,
        amount=signal.amount,
    )
