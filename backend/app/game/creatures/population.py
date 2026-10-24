"""Who lives in the wild places around the starting village, and how they
come back.

Each wild place has its own fauna, drawn once (seeded by the place, so it
never changes) from the bestiary by the dataset's own rules: the place's
biome, how far it is from the village (one trail away is "proxima", two
"intermediaria", more "remota"), the levels allowed at that distance,
rarity weights and the near-village adjustment by kind. Each dawn every
place regrows at most one animal of each of its species, up to the group
size, so a cleared clearing fills again over days.
"""

import json
import random
from collections import deque

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, NPCActivity
from app.db.models.location import Location, LocationConnection
from app.db.models.npc import NPC
from app.game.combat.defense import configure_actor_combat_defense
from app.game.creatures.species import Species, all_species, bestiary, is_active
from app.game.visual.npc import set_npc_stable_identity

DAY = 24 * 60
SPECIES_PER_PLACE = 3
MAX_GROUP = 4
MAX_HOPS = 4

# Location type -> the dataset's biomes.
BIOMES_BY_LOCATION_TYPE = {
    "forest": ("bosques_florestas",),
    "clearing": ("bosques_florestas", "planicies_cultivos"),
    "plains": ("planicies_cultivos",),
    "road": ("planicies_cultivos", "arredores_povoados"),
    "river": ("rios_lagos",),
    "marsh": ("pantanos_mangues",),
    "hills": ("colinas_montanhas",),
    "mountain_range": ("colinas_montanhas", "regioes_frias"),
    "cave": ("cavernas_subterraneo",),
    "mine_entrance": ("cavernas_subterraneo",),
    "abandoned_mine": ("cavernas_subterraneo", "ruinas_estruturas"),
    "ruins": ("ruinas_estruturas",),
    "temple_ruins": ("ruinas_estruturas",),
    "fort_ruins": ("ruinas_estruturas",),
    "tower": ("ruinas_estruturas",),
    "coast": ("costa",),
}
_DISTANCE_BY_HOPS = {1: "proxima", 2: "intermediaria"}
# Level weights by distance. Near the village the dataset's own rule: only
# level 1, a little of level 2.
_LEVEL_WEIGHTS = {
    "proxima": {1: 1.0, 2: 0.15},
    "intermediaria": {1: 0.6, 2: 1.0, 3: 0.4},
    "remota": {1: 0.3, 2: 0.8, 3: 1.0, 4: 0.6, 5: 0.3},
}
_STAGE_WEIGHTS = {"jovem": 0.35, "adulto": 0.55, "velho": 0.10}
# A species' own preferred distance from settlements (dataset) against the
# place's: a "remota" bear never lives one trail from the village.
_DISTANCE_FIT = {
    "proxima": {"proxima": 1.0, "intermediaria": 0.2},
    "intermediaria": {"proxima": 1.0, "intermediaria": 1.0, "remota": 0.3},
    "remota": {"proxima": 0.5, "intermediaria": 1.0, "remota": 1.0},
}


def _rules() -> dict:
    return bestiary()["regras_de_execucao_sugeridas"]["selecao_de_encontros"]


def _distances_from_village(db: Session, campaign_id: str) -> dict[str, int]:
    """Trails from the village people live in to every place within reach."""
    village = (
        db.query(NPC.location_id)
        .filter(NPC.campaign_id == campaign_id, NPC.routine_json != "[]")
        .first()
    )
    if village is None:
        return {}
    hops = {village[0]: 0}
    queue = deque([village[0]])
    while queue:
        here = queue.popleft()
        if hops[here] >= MAX_HOPS:
            continue
        for (there,) in db.query(LocationConnection.to_location_id).filter(
            LocationConnection.from_location_id == here, LocationConnection.active.is_(True)
        ):
            if there not in hops:
                hops[there] = hops[here] + 1
                queue.append(there)
    return hops


def _distance_word(hops: int) -> str:
    return _DISTANCE_BY_HOPS.get(hops, "remota")


def roster(place: Location, hops: int) -> list[Species]:
    """The species that live at this place, always the same for it."""
    biomes = set(BIOMES_BY_LOCATION_TYPE.get(place.type, ()))
    if not biomes:
        return []
    distance = _distance_word(hops)
    rules = _rules()
    rarity_weight = rules["pesos_iniciais_por_raridade"]
    near_kind = rules["ajuste_perto_povoado"] if distance == "proxima" else {}
    candidates = []
    for species in all_species().values():
        if not biomes & set(species.biomes):
            continue
        # The youngest stage decides how close to the village it may live.
        youngest = min(stage.level for stage in species.stages.values())
        level_weight = _LEVEL_WEIGHTS[distance].get(youngest, 0.0)
        weight = (
            level_weight
            * rarity_weight.get(species.rarity, 1)
            * near_kind.get(species.kind, 1.0)
            * _DISTANCE_FIT[distance].get(species.distance, 0.0)
        )
        if weight > 0:
            candidates.append((species, weight))
    rng = random.Random(f"fauna:{place.id}")
    chosen = []
    while candidates and len(chosen) < SPECIES_PER_PLACE:
        species = rng.choices([c[0] for c in candidates], weights=[c[1] for c in candidates])[0]
        chosen.append(species)
        candidates = [c for c in candidates if c[0] is not species]
    return chosen


def _stage_for(species: Species, distance: str, rng: random.Random):
    allowed = {
        key: stage for key, stage in species.stages.items()
        if _LEVEL_WEIGHTS[distance].get(stage.level, 0) > 0
    } or species.stages
    keys = list(allowed)
    return allowed[rng.choices(keys, weights=[_STAGE_WEIGHTS.get(key, 1.0) for key in keys])[0]]


def _spawn(db: Session, campaign_id: str, place: Location, species: Species, distance: str,
           rng: random.Random, hour: int) -> NPC:
    stage = _stage_for(species, distance, rng)
    word = "" if len(species.stages) == 1 or stage.key == "adulto" else f" {stage.key}"
    if word == " velho" and species.feminine:
        word = " velha"
    creature = NPC(
        campaign_id=campaign_id,
        region_id=place.region_id,
        location_id=place.id,
        name=f"{species.singular}{word}",
        role=species.singular.casefold(),
        creature_species=species.key,
        hostility=species.hostility,
        hp_current=stage.hp,
        hp_max=stage.hp,
        activity=NPCActivity.AVAILABLE.value if is_active(species, hour) else NPCActivity.RESTING.value,
        profile_json=json.dumps({"stage": stage.key, "damage": list(stage.damage), "level": stage.level}),
    )
    db.add(creature)
    db.flush()
    if stage.defense:
        configure_actor_combat_defense(db, CombatActorType.NPC, creature.id, armor_rating=stage.defense)
    set_npc_stable_identity(
        db, campaign_id, creature.id, {"creature": f"{species.singular} ({species.kind})", "stage": stage.key}
    )
    return creature


def replenish(db: Session, campaign_id: str, hour: int, *, rng: random.Random | None = None,
              full: bool = False) -> list[NPC]:
    """Regrow the wild: one animal per species and place (``full`` fills
    every group at once, for a new world)."""
    rng = rng or random.Random()
    born = []
    for place_id, hops in _distances_from_village(db, campaign_id).items():
        if hops == 0:
            continue
        place = db.get(Location, place_id)
        species_here = roster(place, hops)
        if not species_here:
            continue
        living = db.query(NPC.creature_species).filter(
            NPC.location_id == place.id, NPC.creature_species.is_not(None), NPC.alive.is_(True)
        ).all()
        counts = {}
        for (key,) in living:
            counts[key] = counts.get(key, 0) + 1
        for species in species_here:
            size = min(MAX_GROUP, species.group[1])
            room = size - counts.get(species.key, 0)
            for _ in range(room if full else min(room, 1)):
                born.append(_spawn(db, campaign_id, place, species, _distance_word(hops), rng, hour))
    db.flush()
    return born


def apply_activity(db: Session, campaign_id: str, hour: int) -> int:
    """Out when their species is active, in the den (not met) otherwise."""
    species_by_key = all_species()
    changed = 0
    for creature in db.query(NPC).filter(
        NPC.campaign_id == campaign_id, NPC.creature_species.is_not(None), NPC.alive.is_(True)
    ):
        species = species_by_key.get(creature.creature_species)
        if species is None:
            continue
        activity = NPCActivity.AVAILABLE.value if is_active(species, hour) else NPCActivity.RESTING.value
        if creature.activity != activity:
            creature.activity = activity
            changed += 1
    return changed
