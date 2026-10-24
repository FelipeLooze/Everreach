"""Who lives in the wild places around the starting village, and how they
come back: each dawn every place regrows at most one animal of each species
up to its habitat's size, so a cleared clearing fills again over days.
"""

import random

from sqlalchemy.orm import Session

from app.core.enums import NPCActivity
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.game.creatures.species import SPECIES, Species, is_active
from app.game.visual.npc import set_npc_stable_identity

DAY = 24 * 60


def _wild_places(db: Session, campaign_id: str) -> list[Location]:
    """Places around every village that has residents (the starting one)."""
    from app.db.models.region import Region

    settled = (
        db.query(NPC.location_id)
        .filter(NPC.campaign_id == campaign_id, NPC.routine_json != "[]")
        .distinct()
        .all()
    )
    subregions = {db.get(Location, location_id).subregion_id for (location_id,) in settled}
    region_ids = [row[0] for row in db.query(Region.id).filter(Region.campaign_id == campaign_id)]
    habitats = {habitat for species in SPECIES.values() for habitat in species.habitats}
    return (
        db.query(Location)
        .filter(
            Location.region_id.in_(region_ids),
            Location.subregion_id.in_(subregions),
            Location.type.in_(habitats),
        )
        .order_by(Location.id)
        .all()
    )


def _spawn(db: Session, campaign_id: str, place: Location, species: Species, rng: random.Random,
           hour: int, taken: set[str]) -> NPC:
    marks = [mark for mark in species.marks if f"{species.singular.capitalize()} {mark}" not in taken]
    name = f"{species.singular.capitalize()} {rng.choice(marks or list(species.marks))}"
    taken.add(name)
    creature = NPC(
        campaign_id=campaign_id,
        region_id=place.region_id,
        location_id=place.id,
        name=name,
        role=species.singular,
        creature_species=species.key,
        hostility=species.hostility,
        hp_current=species.hp,
        hp_max=species.hp,
        activity=NPCActivity.AVAILABLE.value if is_active(species, hour) else NPCActivity.RESTING.value,
    )
    db.add(creature)
    db.flush()
    set_npc_stable_identity(db, campaign_id, creature.id, {"creature": species.english, "detail": name})
    return creature


def replenish(db: Session, campaign_id: str, hour: int, *, rng: random.Random | None = None,
              full: bool = False) -> list[NPC]:
    """Regrow the wild: one animal per species and place (``full`` fills
    every habitat at once, for a new world)."""
    rng = rng or random.Random()
    born = []
    for place in _wild_places(db, campaign_id):
        living = db.query(NPC).filter(
            NPC.location_id == place.id, NPC.creature_species.is_not(None), NPC.alive.is_(True)
        ).all()
        taken = {creature.name for creature in living}
        for species in SPECIES.values():
            room = species.habitats.get(place.type, 0) - sum(c.creature_species == species.key for c in living)
            for _ in range(room if full else min(room, 1)):
                born.append(_spawn(db, campaign_id, place, species, rng, hour, taken))
    db.flush()
    return born


def apply_activity(db: Session, campaign_id: str, hour: int) -> int:
    """Out when their species is active, in the den (not met) otherwise."""
    changed = 0
    for creature in db.query(NPC).filter(
        NPC.campaign_id == campaign_id, NPC.creature_species.is_not(None), NPC.alive.is_(True)
    ):
        species = SPECIES.get(creature.creature_species)
        if species is None:
            continue
        activity = NPCActivity.AVAILABLE.value if is_active(species, hour) else NPCActivity.RESTING.value
        if creature.activity != activity:
            creature.activity = activity
            changed += 1
    return changed
