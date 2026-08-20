from dataclasses import dataclass
from math import isfinite

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.enums import CharacterAttributeKey, EncumbranceTier, ItemLocationType
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.material import MaterialDefinition
from app.game.attributes.service import get_character_attribute


@dataclass(frozen=True)
class EncumbranceRules:
    capacity_per_strength: float = 2.5
    normal_limit: float = 0.50
    lightly_encumbered_limit: float = 0.75
    heavily_encumbered_limit: float = 1.00
    stamina_multipliers: tuple[float, float, float, float] = (1.0, 1.15, 1.35, 1.75)
    agility_penalties: tuple[int, int, int, int] = (0, 1, 2, 4)

    def __post_init__(self) -> None:
        limits = (
            self.normal_limit,
            self.lightly_encumbered_limit,
            self.heavily_encumbered_limit,
        )
        if (
            not isfinite(self.capacity_per_strength)
            or self.capacity_per_strength <= 0
        ):
            raise ValueError("Capacity per strength must be finite and positive.")
        if not all(isfinite(limit) for limit in limits) or not (
            0 <= limits[0] < limits[1] < limits[2]
        ):
            raise ValueError(
                "Encumbrance limits must be finite and strictly increasing."
            )
        if len(self.stamina_multipliers) != 4 or any(
            not isfinite(value) or value < 1 for value in self.stamina_multipliers
        ):
            raise ValueError("Four valid stamina multipliers are required.")
        if len(self.agility_penalties) != 4 or any(
            value < 0 for value in self.agility_penalties
        ):
            raise ValueError("Four non-negative agility penalties are required.")


DEFAULT_ENCUMBRANCE_RULES = EncumbranceRules()


@dataclass(frozen=True)
class EncumbranceSnapshot:
    total_weight: float
    carrying_capacity: float
    load_ratio: float
    tier: EncumbranceTier
    stamina_multiplier: float
    agility_penalty: int


def calculate_encumbrance(
    total_weight: float,
    strength: int,
    rules: EncumbranceRules = DEFAULT_ENCUMBRANCE_RULES,
) -> EncumbranceSnapshot:
    if not isfinite(total_weight) or total_weight < 0:
        raise ValueError("Carried weight cannot be negative.")
    if strength < 0:
        raise ValueError("Strength cannot be negative.")
    capacity = max(rules.capacity_per_strength, strength * rules.capacity_per_strength)
    ratio = total_weight / capacity
    if ratio <= rules.normal_limit:
        tier_index, tier = 0, EncumbranceTier.NORMAL
    elif ratio <= rules.lightly_encumbered_limit:
        tier_index, tier = 1, EncumbranceTier.LIGHTLY_ENCUMBERED
    elif ratio <= rules.heavily_encumbered_limit:
        tier_index, tier = 2, EncumbranceTier.HEAVILY_ENCUMBERED
    else:
        tier_index, tier = 3, EncumbranceTier.OVERLOADED
    return EncumbranceSnapshot(
        total_weight=round(total_weight, 3),
        carrying_capacity=round(capacity, 3),
        load_ratio=round(ratio, 4),
        tier=tier,
        stamina_multiplier=rules.stamina_multipliers[tier_index],
        agility_penalty=rules.agility_penalties[tier_index],
    )


def get_carried_weight(db: Session, character_id: str) -> float:
    value = (
        db.query(
            func.coalesce(
                func.sum(
                    ItemDefinition.base_weight
                    * ItemInstance.quantity
                    * func.coalesce(MaterialDefinition.weight_factor, 1.0)
                ),
                0.0,
            )
        )
        .join(ItemInstance, ItemInstance.definition_id == ItemDefinition.id)
        .outerjoin(
            MaterialDefinition,
            MaterialDefinition.id == ItemInstance.material_id,
        )
        .filter(
            ItemInstance.location_type.in_(
                (
                    ItemLocationType.CHARACTER.value,
                    ItemLocationType.CHARACTER_EQUIPPED.value,
                )
            ),
            ItemInstance.location_ref == character_id,
        )
        .scalar()
    )
    return float(value or 0.0)


def get_character_encumbrance(db: Session, character_id: str) -> EncumbranceSnapshot:
    strength = get_character_attribute(db, character_id, CharacterAttributeKey.STRENGTH)
    return calculate_encumbrance(get_carried_weight(db, character_id), strength.value)
