"""The creatures of Everreach, read from the authoritative bestiary
(app/data/bestiary.json — the user's dataset of 225 creatures and their
loot, imported 2026-10-24).

The backend decides species, place, hours, life and loot; the narrator only
describes. Currency: 1 cobre of the dataset = 1 bronze of the game.

Life stages (the user's call): common fauna comes young, adult or (rarely)
old. "Javali Jovem" in the dataset is the young of the species "Javali":
its values are the young stage, and the adult is derived from them.
"""

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BESTIARY_PATH = Path(__file__).resolve().parents[2] / "data" / "bestiary.json"

# The dataset's activity periods, as hours [start, end).
_PERIOD_HOURS = {
    "amanhecer": ((5, 8),),
    "dia": ((8, 17),),
    "crepusculo": ((17, 20),),
    "noite": ((20, 24), (0, 4)),
    "madrugada": ((0, 5),),
}
# The dataset's aggression codes as the 0-100 hostility the engine uses;
# at combat.hostility.HOSTILE_THRESHOLD (75) and above they attack on sight.
_HOSTILITY = {"baixa": 0, "defensiva": 10, "moderada": 40, "hostil_condicional": 60, "territorial": 80}
_STAGED_KINDS = ("fauna_comum", "fauna_comum_ou_adaptada")
_STAGE_WORDS = {"Jovem": "jovem", "Adulto": "adulto", "Adulta": "adulto"}


@dataclass(frozen=True)
class Stage:
    key: str  # jovem / adulto / velho
    hp: float
    damage: tuple[int, int]
    defense: int
    level: int
    loot_quantity: float  # multiplier on the quantity rolled


@dataclass(frozen=True)
class Loot:
    item_id: str
    item_name: str
    chance_pct: float
    quantity: tuple[int, int]
    method: str
    price_bronze: int
    use: str | None


@dataclass(frozen=True)
class Species:
    key: str  # the dataset id
    singular: str
    plural: str
    feminine: bool
    level: int
    kind: str
    biomes: tuple[str, ...]
    active: tuple[tuple[int, int], ...]
    group: tuple[int, int]
    rarity: str
    distance: str  # proxima / intermediaria / remota
    hostility: int
    behavior: str
    danger: str
    xp: int
    loot: tuple[Loot, ...]
    stages: dict[str, Stage] = field(default_factory=dict)


def is_active(species: Species, hour: int) -> bool:
    return any(start <= hour < end for start, end in species.active)


def _stage_name(name: str) -> tuple[str, str | None]:
    words = name.split()
    if len(words) > 1 and words[-1] in _STAGE_WORDS:
        return " ".join(words[:-1]), _STAGE_WORDS[words[-1]]
    return name, None


def _stages(entry: dict, named_stage: str | None, kind: str) -> dict[str, Stage]:
    combat = entry["combate_proposto"]
    hp = float(combat["hp_max"])
    low, high = combat["dano_por_ataque"]["min"], combat["dano_por_ataque"]["max"]
    defense, level = combat["defesa_fisica_base"], entry["nivel"]
    if named_stage == "jovem":  # the dataset row is the young one
        young = Stage("jovem", hp, (low, high), defense, level, 0.6)
        adult = Stage("adulto", round(hp * 1.5), (low, high + 1), defense + 1, level + 1, 1.0)
    else:
        adult = Stage("adulto", hp, (low, high), defense, level, 1.0)
        young = Stage("jovem", max(1.0, round(hp * 0.6)), (max(0, low - 1), max(0, high - 1)),
                      max(0, defense - 1), max(1, level - 1), 0.6)
    if kind not in _STAGED_KINDS and named_stage is None:
        return {"adulto": adult}
    old = Stage("velho", round(adult.hp * 1.2), adult.damage, adult.defense + 1, adult.level, 1.3)
    return {"jovem": young, "adulto": adult, "velho": old}


@lru_cache(maxsize=1)
def bestiary() -> dict:
    return json.loads(BESTIARY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def all_species() -> dict[str, Species]:
    species = {}
    for entry in bestiary()["monstros"]:
        base_name, named_stage = _stage_name(entry["nome"])
        base_plural, _ = _stage_name(entry["nome_plural"])
        ecology = entry["ecologia"]
        hours = tuple(
            span for period in ecology["atividade"]["periodos_preferidos"] for span in _PERIOD_HOURS.get(period, ())
        ) or ((0, 24),)
        description = entry["descricao"]
        combat = entry["combate_proposto"]
        loot = tuple(
            Loot(
                drop["item_id"], drop["item_nome"], float(drop["chance_base_pct"]),
                (drop["quantidade_min"], drop["quantidade_max"]), drop["metodo_obtencao"],
                drop["preco_base_compra_npc_por_unidade_cobres"], drop.get("uso_potencial"),
            )
            for drop in entry["saques"]
        )
        species[entry["id"]] = Species(
            key=entry["id"],
            singular=base_name,
            plural=base_plural,
            feminine=entry["genero_gramatical"] == "feminino",
            level=entry["nivel"],
            kind=entry["tipo"],
            biomes=tuple(ecology["biomas_compativeis_sugeridos"]),
            active=hours,
            group=(ecology["tamanho_grupo_sugerido"]["min"], ecology["tamanho_grupo_sugerido"]["max"]),
            rarity=ecology["raridade_aparicao_sugerida"],
            distance=ecology["distancia_preferencial_povoado"],
            hostility=_HOSTILITY.get(combat["agressividade_codigo"], 10),
            behavior=description.get("comportamento_fonte") or "",
            danger=description.get("perigo_observavel_fonte") or "",
            xp=combat.get("xp_combate_maximo_base") or 0,
            loot=loot,
            stages=_stages(entry, named_stage, entry["tipo"]),
        )
    return species


def get(key: str | None) -> Species | None:
    return all_species().get(key) if key else None
