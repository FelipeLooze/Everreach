"""Phase 17H — Map Accuracy, Age & Reliability.

A map's own age and reliability are computed on demand from its frozen
content_json (17G) plus the CURRENT state of world truth — never
stored as a single "accuracy score" on the Map row itself (spec: "Only
persist information with clear consumers"; the raw age in world-minutes
and the aspect-level snapshot already ARE the durable facts; everything
here is a read-side computation over them).

MAP AGE: map_age_minutes is a plain subtraction against the current
world clock — old maps are not detected by magic, just arithmetic.

RELIABILITY: a map is only as good as its weakest recorded detail — the
overall precision/certainty estimate is the WORST (lowest-ranked) value
among the aspects it actually recorded, reusing the exact rank
primitives (precision_rank, certainty_rank) 17A/17B already established
rather than inventing a new scoring scale.

STALENESS: find_outdated_map_aspects is the concrete mechanism behind
the spec's Bridge-of-Hal example — a map's frozen statement for one
aspect is compared against the CURRENT canonical KnowledgeFact
statement for the same (subject, aspect). World truth only actually
changes when something calls
app.game.knowledge.geography.update_geographic_fact_statement (also
new in this subphase) — without that, nothing can ever be "outdated"
yet, since a fact's statement was otherwise create-once and immutable.
"""

from sqlalchemy.orm import Session

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowledgeCertainty
from app.db.models.knowledge import KnowledgeFact
from app.db.models.map import Map
from app.game.knowledge.geography import precision_rank
from app.game.knowledge.maps import map_content
from app.game.npcs.service import certainty_rank
from app.game.time.clock import get_world_time


def map_age_minutes(db: Session, campaign_id: str, map_row: Map) -> int:
    return get_world_time(db, campaign_id).total_minutes() - map_row.created_world_minute


def map_reliability_precision(map_row: Map) -> GeographicPrecision | None:
    content = map_content(map_row)
    ranked = [
        GeographicPrecision(a["precision"])
        for a in content["aspects"]
        if a["precision"] is not None
    ]
    if not ranked:
        return None
    return min(ranked, key=precision_rank)


def map_reliability_certainty(map_row: Map) -> KnowledgeCertainty | None:
    content = map_content(map_row)
    ranked = [KnowledgeCertainty(a["certainty"]) for a in content["aspects"]]
    if not ranked:
        return None
    return min(ranked, key=certainty_rank)


def find_outdated_map_aspects(db: Session, campaign_id: str, map_row: Map) -> set[GeographicKnowledgeAspect]:
    """Compares each aspect frozen on the map against the CURRENT fact
    with that exact fact_key. Rumor-sourced entries (is_rumor, stored on
    the snapshot itself — see app.game.knowledge.cartography.SurveyedAspect)
    are skipped: rumors were never Canon to begin with, so "outdated"
    doesn't apply to them the same way; only canonical aspect facts can
    drift, and only via a deliberate
    app.game.knowledge.geography.update_geographic_fact_statement call."""
    content = map_content(map_row)
    outdated: set[GeographicKnowledgeAspect] = set()
    for entry in content["aspects"]:
        if entry.get("is_rumor"):
            continue
        current = (
            db.query(KnowledgeFact)
            .filter(KnowledgeFact.campaign_id == campaign_id, KnowledgeFact.fact_key == entry["fact_key"])
            .first()
        )
        if current is None:
            continue
        if current.statement != entry["statement"]:
            outdated.add(GeographicKnowledgeAspect(entry["aspect"]))
    return outdated
