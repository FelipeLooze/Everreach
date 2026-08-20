from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models.character import Character
from app.db.models.domain import (
    CharacterDomainEvidence,
    CharacterDomainSynergy,
    DomainDefinition,
)
from app.game.domains.service import DomainMaturity, domain_maturity


MIN_DOMAIN_DEPTH = 3.0
MIN_DOMAIN_CONSISTENCY = 2
MIN_DOMAIN_DIVERSITY = 2
MIN_SYNERGY_DEPTH = 1.0
MAX_CLASS_DOMAINS = 4
MAX_CLASS_PATH_CANDIDATES = 64


@dataclass(frozen=True)
class DomainAssessment:
    domain_key: str
    family: str
    depth: float
    consistency: int
    diversity: int
    synergy_depth: float
    synergy_count: int
    score: float
    eligible: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class SynergyAssessment:
    domains: tuple[str, str]
    depth: float
    evidence_count: int
    score: float
    eligible: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class MatureClassPath:
    domains: tuple[str, ...]
    integrations: tuple[tuple[str, str], ...]
    score: float

    @property
    def generation_key(self) -> str:
        return "domains:" + "+".join(self.domains)


@dataclass(frozen=True)
class ClassPathResolution:
    """Internal mechanical explanation; it must never enter the LLM context."""

    domains: tuple[DomainAssessment, ...]
    synergies: tuple[SynergyAssessment, ...]
    candidates: tuple[MatureClassPath, ...]


def resolve_class_paths(
    db: Session,
    character: Character,
) -> ClassPathResolution:
    """Resolve class eligibility from persisted facts without consulting the LLM."""
    evidence_rows = (
        db.query(CharacterDomainEvidence)
        .filter(CharacterDomainEvidence.character_id == character.id)
        .order_by(CharacterDomainEvidence.domain_key)
        .all()
    )
    definitions = {
        row.key: row
        for row in db.query(DomainDefinition)
        .filter(
            DomainDefinition.key.in_(
                [evidence.domain_key for evidence in evidence_rows]
            )
        )
        .all()
    }

    domain_assessments = tuple(
        _assess_domain(
            domain_maturity(db, character.id, evidence.domain_key),
            definitions.get(evidence.domain_key),
        )
        for evidence in evidence_rows
    )
    mature_domains = {
        assessment.domain_key: assessment
        for assessment in domain_assessments
        if assessment.eligible
    }

    synergy_rows = (
        db.query(CharacterDomainSynergy)
        .filter(CharacterDomainSynergy.character_id == character.id)
        .order_by(
            CharacterDomainSynergy.first_domain_key,
            CharacterDomainSynergy.second_domain_key,
        )
        .all()
    )
    synergy_assessments = tuple(
        _assess_synergy(row, mature_domains) for row in synergy_rows
    )
    eligible_edges = {
        assessment.domains: assessment
        for assessment in synergy_assessments
        if assessment.eligible
    }

    candidates = _build_candidates(mature_domains, eligible_edges)
    return ClassPathResolution(
        domains=domain_assessments,
        synergies=synergy_assessments,
        candidates=tuple(candidates[:MAX_CLASS_PATH_CANDIDATES]),
    )


def _assess_domain(
    maturity: DomainMaturity,
    definition: DomainDefinition | None,
) -> DomainAssessment:
    reasons: list[str] = []
    if definition is None:
        reasons.append("unknown_domain")
    if maturity.depth < MIN_DOMAIN_DEPTH:
        reasons.append("insufficient_depth")
    if maturity.consistency < MIN_DOMAIN_CONSISTENCY:
        reasons.append("insufficient_consistency")
    if maturity.diversity < MIN_DOMAIN_DIVERSITY:
        reasons.append("insufficient_diversity")

    score = (
        min(maturity.depth / MIN_DOMAIN_DEPTH, 2.0)
        + min(maturity.consistency / MIN_DOMAIN_CONSISTENCY, 2.0)
        + min(maturity.diversity / MIN_DOMAIN_DIVERSITY, 2.0)
    )
    return DomainAssessment(
        domain_key=maturity.domain_key,
        family=definition.family if definition is not None else "UNKNOWN",
        depth=maturity.depth,
        consistency=maturity.consistency,
        diversity=maturity.diversity,
        synergy_depth=maturity.synergy_depth,
        synergy_count=maturity.synergy_count,
        score=round(score, 6),
        eligible=not reasons,
        rejection_reasons=tuple(reasons),
    )


def _assess_synergy(
    row: CharacterDomainSynergy,
    mature_domains: dict[str, DomainAssessment],
) -> SynergyAssessment:
    domains = tuple(sorted((row.first_domain_key, row.second_domain_key)))
    reasons: list[str] = []
    if domains[0] == domains[1]:
        reasons.append("same_domain")
    if not set(domains) <= set(mature_domains):
        reasons.append("domain_not_mature")
    if row.depth < MIN_SYNERGY_DEPTH:
        reasons.append("insufficient_synergy_depth")
    if row.evidence_count < 1:
        reasons.append("missing_synergy_evidence")

    score = min(row.depth / MIN_SYNERGY_DEPTH, 2.0) + min(
        row.evidence_count,
        2,
    )
    return SynergyAssessment(
        domains=domains,
        depth=row.depth,
        evidence_count=row.evidence_count,
        score=round(score, 6),
        eligible=not reasons,
        rejection_reasons=tuple(reasons),
    )


def _build_candidates(
    mature_domains: dict[str, DomainAssessment],
    eligible_edges: dict[tuple[str, str], SynergyAssessment],
) -> list[MatureClassPath]:
    integrated_sets = _limit_domain_sets(
        {frozenset(edge) for edge in eligible_edges},
        mature_domains,
        eligible_edges,
    )
    frontier = set(integrated_sets)
    while frontier:
        expanded: set[frozenset[str]] = set()
        for domains in frontier:
            if len(domains) >= MAX_CLASS_DOMAINS:
                continue
            for edge in eligible_edges:
                edge_domains = frozenset(edge)
                if domains & edge_domains and not edge_domains <= domains:
                    candidate = domains | edge_domains
                    if len(candidate) <= MAX_CLASS_DOMAINS:
                        expanded.add(candidate)
        expanded -= integrated_sets
        if not expanded:
            break
        expanded = _limit_domain_sets(
            expanded,
            mature_domains,
            eligible_edges,
        )
        integrated_sets |= expanded
        integrated_sets = _limit_domain_sets(
            integrated_sets,
            mature_domains,
            eligible_edges,
        )
        frontier = expanded & integrated_sets

    paths: list[MatureClassPath] = []
    for domain_set in integrated_sets:
        domains = tuple(sorted(domain_set))
        integrations = tuple(
            sorted(edge for edge in eligible_edges if set(edge) <= domain_set)
        )
        paths.append(
            MatureClassPath(
                domains=domains,
                integrations=integrations,
                score=_path_score(
                    domains,
                    integrations,
                    mature_domains,
                    eligible_edges,
                ),
            )
        )
    for domain_key, assessment in mature_domains.items():
        paths.append(
            MatureClassPath(
                domains=(domain_key,),
                integrations=(),
                score=assessment.score,
            )
        )

    return sorted(
        paths,
        key=lambda path: (-path.score, -len(path.domains), path.domains),
    )


def _limit_domain_sets(
    domain_sets: set[frozenset[str]],
    mature_domains: dict[str, DomainAssessment],
    eligible_edges: dict[tuple[str, str], SynergyAssessment],
) -> set[frozenset[str]]:
    ranked = sorted(
        domain_sets,
        key=lambda domain_set: (
            -_path_score(
                tuple(sorted(domain_set)),
                tuple(
                    sorted(
                        edge
                        for edge in eligible_edges
                        if set(edge) <= domain_set
                    )
                ),
                mature_domains,
                eligible_edges,
            ),
            tuple(sorted(domain_set)),
        ),
    )
    return set(ranked[:MAX_CLASS_PATH_CANDIDATES])


def _path_score(
    domains: tuple[str, ...],
    integrations: tuple[tuple[str, str], ...],
    mature_domains: dict[str, DomainAssessment],
    eligible_edges: dict[tuple[str, str], SynergyAssessment],
) -> float:
    domain_score = sum(mature_domains[key].score for key in domains)
    integration_score = sum(eligible_edges[edge].score for edge in integrations)
    breadth_bonus = 0.5 * (len(domains) - 1)
    return round(domain_score + integration_score + breadth_bonus, 6)
