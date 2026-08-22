"""Phase 17F — Cartography Foundation.

"A character cannot create an accurate map of somewhere they know
nothing about" (spec) is the one hard rule this subphase establishes as
code, not just prose: survey_cartographic_knowledge reads a
knower's OWN current geographic knowledge (17A/17B — which aspects,
each aspect's statement and precision) for one entity, and that survey
IS the raw material 17G's physical maps are drawn from. A map's content
is never a live reference back to KnowledgeFact/KnowledgeKnower — it is
a frozen copy of exactly this survey, taken once, at creation time
(spec's "MAP DATA != WORLD TRUTH").

Cartography is deliberately NOT a universal skill roll here. Phase 8
(professions/attributes/domains) and Phase 11 (techniques) already
own progression — nothing in this module invents a parallel
"Cartography Skill". What IS built is the one piece those systems don't
already provide: a reusable way to ask "given what this character
currently knows, what could they actually put on a map?" — richer
quality bonuses from a relevant profession/technique/tool are a real,
deferred follow-up (spec explicitly allows it), not required for the
foundation.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.game.knowledge.geography import geographic_subject

# A map without at least existence + one spatial aspect isn't a map of
# anything — it's just "I've heard the name", not enough to draw.
_SPATIAL_ASPECTS = (
    GeographicKnowledgeAspect.DIRECTION,
    GeographicKnowledgeAspect.DISTANCE,
    GeographicKnowledgeAspect.ROUTE,
)


@dataclass
class SurveyedAspect:
    aspect: GeographicKnowledgeAspect
    statement: str
    precision: GeographicPrecision | None
    certainty: str
    fact_key: str
    is_rumor: bool


@dataclass
class CartographicSurvey:
    subject_kind: str
    entity_id: str
    aspects: list[SurveyedAspect] = field(default_factory=list)

    @property
    def can_produce_map(self) -> bool:
        known = {surveyed.aspect for surveyed in self.aspects}
        if GeographicKnowledgeAspect.EXISTENCE not in known:
            return False
        return any(aspect in known for aspect in _SPATIAL_ASPECTS)


def survey_cartographic_knowledge(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subject_kind: str,
    entity_id: str,
) -> CartographicSurvey:
    subject = geographic_subject(subject_kind, entity_id)
    rows = (
        db.query(KnowledgeFact, KnowledgeKnower)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.subject == subject,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .all()
    )

    prefix = f"{subject}:"
    survey = CartographicSurvey(subject_kind=subject_kind, entity_id=entity_id)
    for fact, knower in rows:
        if not fact.fact_key.startswith(prefix):
            continue
        raw_aspect = fact.fact_key[len(prefix):].split(":", 1)[0]
        try:
            aspect = GeographicKnowledgeAspect(raw_aspect.upper())
        except ValueError:
            continue
        survey.aspects.append(
            SurveyedAspect(
                aspect=aspect,
                statement=fact.statement,
                precision=GeographicPrecision(knower.precision) if knower.precision else None,
                certainty=knower.certainty,
                fact_key=fact.fact_key,
                is_rumor=":rumor:" in fact.fact_key,
            )
        )
    return survey
