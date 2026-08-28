"""S1.3 — lazy, backend-authorized economic Canon.

The LLM may propose a missing base value; it never writes Canon.  Existing
persisted and deterministic Phase 14 values always win.  Accepted proposals
are validated, deduplicated and persisted once, while quality, condition,
local supply and explicit offers remain deterministic current-price concerns.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.llm_call import call_llm
from app.ai.llm_service import LLMService, LLMServiceError
from app.core.logging import get_logger
from app.db.models.economic_value import EconomicCanonValue
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.local_economy import LocationEconomy
from app.db.models.location import Location
from app.game.economy.pricing import resolve_market_price
from app.game.economy.supply_demand import resolve_local_market_price
from app.game.time.clock import get_world_time


logger = get_logger("game")
MAX_MUNDANE_BASE_PRICE_BRONZE = 9_999
MAX_EXCEPTIONAL_BASE_PRICE_BRONZE = 100_000_000
MAX_RATIONALE_LENGTH = 500
_SERVICE_MULTIPLIER_MIN = 0.5
_SERVICE_MULTIPLIER_MAX = 2.0


class EconomicClassification(str, Enum):
    MARKET_PRICE = "MARKET_PRICE"
    NOT_FOR_SALE = "NOT_FOR_SALE"
    NO_ESTABLISHED_MARKET = "NO_ESTABLISHED_MARKET"
    NEGOTIATED_ONLY = "NEGOTIATED_ONLY"
    UNIQUE_OR_PRICELESS = "UNIQUE_OR_PRICELESS"


class EconomicProvenance(str, Enum):
    SEEDED = "SEEDED"
    DETERMINISTIC = "DETERMINISTIC"
    LLM_PROPOSED = "LLM_PROPOSED"
    CRAFT_DERIVED = "CRAFT_DERIVED"
    WORLD_EVENT = "WORLD_EVENT"
    CANON_OVERRIDE = "CANON_OVERRIDE"


class EconomicSubjectType(str, Enum):
    ITEM_DEFINITION = "ITEM_DEFINITION"
    ITEM_INSTANCE = "ITEM_INSTANCE"
    SERVICE = "SERVICE"


class EconomicCanonError(ValueError):
    pass


class EconomicProposalUnavailable(EconomicCanonError):
    pass


@dataclass(frozen=True)
class EconomicSubject:
    campaign_id: str
    subject_type: EconomicSubjectType
    subject_id: str
    name: str
    category: str
    location_id: str | None = None
    provider_type: str | None = None
    provider_id: str | None = None
    item_definition_id: str | None = None
    item_instance_id: str | None = None
    service_unit: str | None = None
    rarity: str | None = None
    magical: bool = False
    unique: bool = False
    production_difficulty: str | None = None

    @property
    def canonical_key(self) -> str:
        if self.subject_type == EconomicSubjectType.SERVICE:
            return f"SERVICE:{self.location_id}:{self.subject_id}".lower()
        return f"{self.subject_type.value}:{self.subject_id}".lower()


@dataclass(frozen=True)
class EconomicValueResolution:
    classification: EconomicClassification
    base_price_bronze: int | None
    provenance: EconomicProvenance
    canonical_key: str
    rationale: str = ""
    record_id: str | None = None
    reused: bool = False


@dataclass(frozen=True)
class CurrentEconomicPrice:
    base_price_bronze: int
    current_price_bronze: int
    classification: EconomicClassification


def item_subject(
    campaign_id: str,
    item: ItemDefinition | ItemInstance,
    *,
    location_id: str | None = None,
    magical: bool = False,
    unique: bool = False,
    rarity: str | None = None,
) -> EconomicSubject:
    instance = item if isinstance(item, ItemInstance) else None
    definition = instance.definition if instance is not None else item
    use_instance = unique and instance is not None
    return EconomicSubject(
        campaign_id=campaign_id,
        subject_type=(EconomicSubjectType.ITEM_INSTANCE if use_instance else EconomicSubjectType.ITEM_DEFINITION),
        subject_id=(instance.id if use_instance else definition.id),
        name=definition.name,
        category=definition.type,
        location_id=location_id,
        item_definition_id=definition.id,
        item_instance_id=instance.id if instance else None,
        rarity=rarity,
        magical=magical,
        unique=unique,
    )


def service_subject(
    campaign_id: str,
    location_id: str,
    service_key: str,
    name: str,
    *,
    unit: str | None = None,
    provider_type: str | None = None,
    provider_id: str | None = None,
) -> EconomicSubject:
    normalized_key = _normalized_identifier(service_key)
    return EconomicSubject(
        campaign_id=campaign_id,
        subject_type=EconomicSubjectType.SERVICE,
        subject_id=normalized_key,
        name=_clean_text(name, "Economic subject name"),
        category="SERVICE",
        location_id=location_id,
        provider_type=provider_type,
        provider_id=provider_id,
        service_unit=_clean_optional_text(unit),
    )


def materialize_economic_value(
    db: Session,
    subject: EconomicSubject,
    *,
    llm_service: LLMService | None = None,
) -> EconomicValueResolution:
    """Resolve persisted -> deterministic -> LLM proposal, in that order."""
    existing = _get_record(db, subject.canonical_key)
    if existing is not None:
        logger.debug("economic canon reused key=%s provenance=%s", subject.canonical_key, existing.provenance)
        return _resolution_from_record(existing, reused=True)

    deterministic = _deterministic_value(db, subject)
    if deterministic is not None:
        logger.debug("economic canon deterministic key=%s", subject.canonical_key)
        return deterministic

    if llm_service is None:
        raise EconomicProposalUnavailable("Missing economic value requires an LLM proposal provider.")

    context = build_economic_context(db, subject)
    try:
        raw = call_llm(
            llm_service,
            _ECONOMIC_SYSTEM_PROMPT,
            json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            purpose="ECONOMIC_PRICE_PROPOSAL",
        )
    except LLMServiceError as exc:
        logger.debug("economic proposal unavailable key=%s error=%s", subject.canonical_key, type(exc).__name__)
        raise EconomicProposalUnavailable("Economic price proposal provider is unavailable.") from exc
    proposal = validate_proposal(raw, subject, context)
    record = _persist_once(db, subject, proposal)
    if subject.item_definition_id and record.classification == EconomicClassification.MARKET_PRICE.value:
        definition = db.get(ItemDefinition, subject.item_definition_id)
        if definition is not None and definition.base_value_bronze is None:
            definition.base_value_bronze = record.base_price_bronze
            db.flush()
    logger.debug(
        "economic proposal accepted key=%s classification=%s base=%s",
        subject.canonical_key,
        record.classification,
        record.base_price_bronze,
    )
    return _resolution_from_record(record, reused=record.provenance != EconomicProvenance.LLM_PROPOSED.value)


def validate_proposal(
    raw: str,
    subject: EconomicSubject,
    context: dict[str, object] | None = None,
) -> EconomicValueResolution:
    try:
        payload = json.loads(_strip_code_fence(raw))
    except (TypeError, json.JSONDecodeError) as exc:
        raise EconomicCanonError("Economic proposal is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise EconomicCanonError("Economic proposal must be a JSON object.")
    try:
        classification = EconomicClassification(payload.get("classification"))
    except (TypeError, ValueError) as exc:
        raise EconomicCanonError("Economic proposal has an unsupported classification.") from exc
    price = payload.get("base_price_bronze")
    if classification == EconomicClassification.MARKET_PRICE:
        if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
            raise EconomicCanonError("Market price must be a positive integer Bronze amount.")
        exceptional = subject.magical or subject.unique or (subject.rarity or "").upper() in {
            "RARE", "EPIC", "LEGENDARY", "UNIQUE",
        }
        ceiling = MAX_EXCEPTIONAL_BASE_PRICE_BRONZE if exceptional else MAX_MUNDANE_BASE_PRICE_BRONZE
        if price > ceiling:
            raise EconomicCanonError("Proposed price is implausible for this economic subject.")
    elif price is not None:
        raise EconomicCanonError("Non-market classifications cannot include a numeric price.")
    rationale = _clean_optional_text(payload.get("rationale"))
    if len(rationale) > MAX_RATIONALE_LENGTH:
        raise EconomicCanonError("Economic proposal rationale is too long.")
    return EconomicValueResolution(
        classification=classification,
        base_price_bronze=price,
        provenance=EconomicProvenance.LLM_PROPOSED,
        canonical_key=subject.canonical_key,
        rationale=rationale,
    )


def build_economic_context(db: Session, subject: EconomicSubject) -> dict[str, object]:
    location = db.get(Location, subject.location_id) if subject.location_id else None
    economy = (
        db.query(LocationEconomy).filter(LocationEconomy.location_id == subject.location_id).one_or_none()
        if subject.location_id else None
    )
    item = db.get(ItemInstance, subject.item_instance_id) if subject.item_instance_id else None
    definition = db.get(ItemDefinition, subject.item_definition_id) if subject.item_definition_id else None
    subject_context: dict[str, object] = {
        "name": subject.name,
        "subject_type": subject.subject_type.value,
        "category": subject.category,
        "service_unit": subject.service_unit,
        "rarity": subject.rarity,
        "magical": subject.magical,
        "unique": subject.unique,
        "production_difficulty": subject.production_difficulty,
    }
    if definition is not None:
        subject_context.update({"description": definition.description or None, "base_weight": definition.base_weight})
    if item is not None:
        subject_context.update({
            "quality": item.quality,
            "durability_current": item.durability_current,
            "durability_max": item.durability_max,
            "quantity": item.quantity,
        })
    return {
        "subject": {key: value for key, value in subject_context.items() if value is not None},
        "location": ({"name": location.name, "type": location.type} if location else None),
        "local_economy": ({"wealth_band": economy.wealth_band} if economy else None),
        "provider": (
            {"type": subject.provider_type, "id": subject.provider_id}
            if subject.provider_type and subject.provider_id else None
        ),
        "currency": {
            "bronze_per_silver": 100,
            "silver_per_gold": 100,
            "bronze_per_gold": 10_000,
            "anchors": {
                "tiny_expense_bronze": "1-5",
                "ordinary_low_value_bronze": "5-15",
                "normal_labor_per_day_bronze": "5-10",
                "artisan_labor_per_day_bronze": "10-20",
                "specialized_labor_bronze": "15-30+",
            },
        },
    }


def current_price(
    db: Session,
    value: EconomicValueResolution,
    *,
    item_instance: ItemInstance | None = None,
    location_id: str | None = None,
    service_modifier: float = 1.0,
) -> CurrentEconomicPrice | None:
    if value.classification != EconomicClassification.MARKET_PRICE or value.base_price_bronze is None:
        return None
    if item_instance is not None:
        amount = (
            resolve_local_market_price(db, item_instance, location_id)
            if location_id else resolve_market_price(db, item_instance)
        )
    else:
        bounded = max(_SERVICE_MULTIPLIER_MIN, min(_SERVICE_MULTIPLIER_MAX, service_modifier))
        amount = max(1, round(value.base_price_bronze * bounded))
    return CurrentEconomicPrice(value.base_price_bronze, amount, value.classification)


def get_service_value(db: Session, location_id: str, service_key: str) -> EconomicValueResolution | None:
    record = _get_record(db, f"service:{location_id}:{_normalized_identifier(service_key)}")
    return _resolution_from_record(record, reused=True) if record else None


def override_service_value(
    db: Session,
    campaign_id: str,
    location_id: str,
    service_key: str,
    price_bronze: int,
    *,
    name: str,
) -> EconomicValueResolution:
    subject = service_subject(campaign_id, location_id, service_key, name)
    proposal = validate_proposal(
        json.dumps({"classification": "MARKET_PRICE", "base_price_bronze": price_bronze, "rationale": ""}),
        subject,
    )
    proposal = EconomicValueResolution(
        proposal.classification, proposal.base_price_bronze, EconomicProvenance.CANON_OVERRIDE,
        proposal.canonical_key, proposal.rationale,
    )
    return _resolution_from_record(_persist_once(db, subject, proposal))


def _deterministic_value(db: Session, subject: EconomicSubject) -> EconomicValueResolution | None:
    if subject.item_definition_id:
        definition = db.get(ItemDefinition, subject.item_definition_id)
        if definition is not None and definition.base_value_bronze is not None:
            classification = (
                EconomicClassification.MARKET_PRICE
                if definition.base_value_bronze > 0 else EconomicClassification.NOT_FOR_SALE
            )
            return EconomicValueResolution(
                classification,
                definition.base_value_bronze if definition.base_value_bronze > 0 else None,
                EconomicProvenance.DETERMINISTIC,
                subject.canonical_key,
                reused=True,
            )
    return None


def _persist_once(
    db: Session, subject: EconomicSubject, value: EconomicValueResolution
) -> EconomicCanonValue:
    existing = _get_record(db, subject.canonical_key)
    if existing is not None:
        return existing
    record = EconomicCanonValue(
        campaign_id=subject.campaign_id,
        canonical_key=subject.canonical_key,
        subject_type=subject.subject_type.value,
        subject_id=subject.subject_id,
        location_id=subject.location_id,
        provider_type=subject.provider_type,
        provider_id=subject.provider_id,
        classification=value.classification.value,
        base_price_bronze=value.base_price_bronze,
        provenance=value.provenance.value,
        rationale=value.rationale,
        created_world_minute=get_world_time(db, subject.campaign_id).total_minutes(),
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError:
        existing = _get_record(db, subject.canonical_key)
        if existing is None:
            raise
        return existing
    return record


def _get_record(db: Session, canonical_key: str) -> EconomicCanonValue | None:
    return db.query(EconomicCanonValue).filter(EconomicCanonValue.canonical_key == canonical_key).one_or_none()


def _resolution_from_record(record: EconomicCanonValue, *, reused: bool = False) -> EconomicValueResolution:
    return EconomicValueResolution(
        EconomicClassification(record.classification),
        record.base_price_bronze,
        EconomicProvenance(record.provenance),
        record.canonical_key,
        record.rationale,
        record.id,
        reused,
    )


def _normalized_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "_", value.strip().casefold()).strip("_")
    if not normalized:
        raise EconomicCanonError("Economic subject identifier is required.")
    return normalized[:80]


def _clean_text(value: object, field: str) -> str:
    cleaned = " ".join(str(value).split()) if value is not None else ""
    if not cleaned:
        raise EconomicCanonError(f"{field} is required.")
    return cleaned


def _clean_optional_text(value: object) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


_ECONOMIC_SYSTEM_PROMPT = """You propose a missing canonical BASE economic value for a persistent RPG world.
Return exactly one JSON object with: classification, base_price_bronze, rationale.
classification must be MARKET_PRICE, NOT_FOR_SALE, NO_ESTABLISHED_MARKET,
NEGOTIATED_ONLY, or UNIQUE_OR_PRICELESS. MARKET_PRICE requires a positive integer
Bronze amount; every other classification requires null. Rationale is one short
observability sentence, never hidden reasoning. Currency: 100 Bronze = 1 Silver,
100 Silver = 1 Gold. Use only supplied facts. You propose; the backend validates."""
