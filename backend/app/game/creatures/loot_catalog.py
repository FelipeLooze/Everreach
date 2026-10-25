"""Authoritative item catalog and buyer categories for bestiary loot."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.enums import ItemInstanceMode, ItemType
from app.db.models.item import ItemDefinition
from app.game.economy.pricing import set_item_base_value
from app.game.items.service import create_item_definition
from app.game.creatures.species import all_species


FOOD_AND_HIDE = "FOOD_AND_HIDE"
HARD_MATERIAL = "HARD_MATERIAL"
NATURAL_REAGENT = "NATURAL_REAGENT"
ANY_BESTIARY_LOOT = "ANY_BESTIARY_LOOT"


@dataclass(frozen=True)
class BestiaryItem:
    item_id: str
    key: str
    name: str
    price_bronze: int
    use: str | None
    methods: frozenset[str]
    purchase_categories: frozenset[str]

    @property
    def sellable(self) -> bool:
        return self.price_bronze > 0 or bool(self.use)

    @property
    def effective_price_bronze(self) -> int:
        if self.price_bronze > 0:
            return self.price_bronze
        return 1 if self.use else 0


def bestiary_item_key(item_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", item_id.casefold()).strip("_")


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _display_name(item_id: str, dataset_name: str) -> str:
    if "\ufffd" not in dataset_name:
        return dataset_name
    words = item_id.removeprefix("IT-EVR-").replace("-", " ").casefold()
    return words[:1].upper() + words[1:]


_FOOD_HIDE_WORDS = {
    "carne", "pele", "pelagem", "couro", "gordura", "ovo", "ovos",
    "mel", "leite", "file", "peixe", "lombo",
}
_HARD_WORDS = {
    "presa", "presas", "osso", "ossos", "chifre", "chifres", "dente",
    "dentes", "incisivo", "garra", "garras", "casco", "cascos", "escama",
    "escamas", "carapaca", "quitina", "quitinosas", "espinho", "espinhos",
    "bico", "mandibula", "corno", "unha", "unhas", "placa", "placas",
}
_REAGENT_WORDS = {
    "erva", "folha", "folhas", "raiz", "raizes", "flor", "flores", "seiva",
    "resina", "po", "veneno", "glandula", "oleo", "essencia", "esporo",
    "esporos", "fungo", "liquen", "sangue", "bile", "saliva", "pigmento",
    "cristal", "nucleo", "coracao", "olho", "olhos", "antena", "antenas",
    "asa", "asas", "pluma", "plumas", "pena", "penas", "musgo", "gel",
    "toxina", "fluido", "membrana", "saco", "bolsa", "seda",
}


def _categories(item_id: str, use: str | None) -> frozenset[str]:
    words = set(re.findall(r"[a-z0-9]+", _plain(f"{item_id} {use or ''}")))
    categories = set()
    if words & _FOOD_HIDE_WORDS:
        categories.add(FOOD_AND_HIDE)
    if words & _HARD_WORDS:
        categories.add(HARD_MATERIAL)
    if words & _REAGENT_WORDS:
        categories.add(NATURAL_REAGENT)
    return frozenset(categories)


@lru_cache(maxsize=1)
def all_bestiary_items() -> dict[str, BestiaryItem]:
    accumulated: dict[str, dict] = {}
    for species in all_species().values():
        for drop in species.loot:
            key = bestiary_item_key(drop.item_id)
            row = accumulated.setdefault(
                key,
                {
                    "item_id": drop.item_id,
                    "name": _display_name(drop.item_id, drop.item_name),
                    "price": drop.price_bronze,
                    "uses": [],
                    "methods": set(),
                },
            )
            if drop.use and drop.use not in row["uses"]:
                row["uses"].append(drop.use)
            row["methods"].add(drop.method)
    return {
        key: BestiaryItem(
            item_id=row["item_id"],
            key=key,
            name=row["name"],
            price_bronze=row["price"],
            use="; ".join(row["uses"]) or None,
            methods=frozenset(row["methods"]),
            purchase_categories=_categories(
                row["item_id"], "; ".join(row["uses"]) or None
            ),
        )
        for key, row in accumulated.items()
    }


def bestiary_item_for_definition(
    definition: ItemDefinition,
) -> BestiaryItem | None:
    return all_bestiary_items().get(definition.key)


def ensure_bestiary_item_definitions(
    db: Session,
) -> dict[str, ItemDefinition]:
    """Materialize every unique dataset item through the item foundation."""
    catalog = all_bestiary_items()
    definitions = {
        definition.key: definition
        for definition in db.query(ItemDefinition).filter(
            ItemDefinition.key.in_(tuple(catalog))
        )
    }
    for item in catalog.values():
        definition = definitions.get(item.key)
        if definition is None:
            definition = create_item_definition(
                db,
                key=item.key,
                name=item.name,
                item_type=ItemType.MATERIAL,
                instance_mode=ItemInstanceMode.STACKABLE,
                description=(
                    f"Material obtido de criatura. Uso potencial: {item.use}."
                    if item.use
                    else "Material obtido de criatura sem uso comercial conhecido."
                ),
                base_weight=0.0,
            )
        if definition.base_value_bronze is None:
            set_item_base_value(db, definition, item.effective_price_bronze)
        definitions[item.key] = definition
    db.flush()
    return definitions
