"""Small, explicit production catalog for the first playable economy.

Recipes are rules, not world objects: inputs and outputs are still real Phase
10 item instances, while place, time and professional learning are resolved by
``playable.py``.  Keeping this catalog in code avoids pretending every recipe
is already known lore while leaving a clean seam for learned recipes later.
"""

from dataclasses import dataclass

from app.core.enums import ToolCapability


@dataclass(frozen=True)
class EconomyRecipe:
    key: str
    name: str
    description: str
    location_types: tuple[str, ...]
    inputs: tuple[tuple[str, int], ...]
    outputs: tuple[tuple[str, int], ...]
    minutes: int
    profession_key: str
    profession_name: str
    profession_xp: float
    required_tool: ToolCapability | None = None


RECIPES: tuple[EconomyRecipe, ...] = (
    EconomyRecipe(
        key="prepare_travel_rations",
        name="Preparar Rações de Viagem",
        description="Conservar carne e preparar duas porções próprias para a estrada.",
        location_types=("inn", "tavern", "restaurant"),
        inputs=(("Carne Seca", 1),),
        outputs=(("Ração de Viagem", 2),),
        minutes=90,
        profession_key="COOK",
        profession_name="Cozinheiro",
        profession_xp=0.6,
    ),
    EconomyRecipe(
        key="braid_rope",
        name="Trançar Corda",
        description="Trançar fibras vegetais até formar uma corda resistente.",
        location_types=("general_store", "merchants_guild", "warehouse"),
        inputs=(("Fibra Vegetal", 3),),
        outputs=(("Corda", 1),),
        minutes=60,
        profession_key="ARTISAN",
        profession_name="Artesão",
        profession_xp=0.4,
    ),
    EconomyRecipe(
        key="forge_iron_knife",
        name="Forjar Faca de Ferro",
        description="Forjar uma faca simples usando ferro bruto e madeira para o cabo.",
        location_types=("blacksmith",),
        inputs=(("Ferro Bruto", 2), ("Madeira de Oficina", 1)),
        outputs=(("Faca de Ferro", 1),),
        minutes=180,
        profession_key="BLACKSMITH",
        profession_name="Ferreiro",
        profession_xp=1.0,
        required_tool=ToolCapability.HAMMERING,
    ),
)


def recipe_by_key(key: str) -> EconomyRecipe | None:
    normalized = key.strip().casefold()
    return next((recipe for recipe in RECIPES if recipe.key.casefold() == normalized), None)
