"""The people who live in the starting village, and where each one is at
every hour.

Starting village, part 2 (2026-10-24): about 15 residents beyond the five
who run the village, each with a home and a daily routine, so the square,
the inn and the forge change with the time of day. Roles are fixed; names,
sex, age and personality are sorted per save.

A routine is a list of [from_hour, to_hour, place]:
- "home": in their house, not met anywhere (also asleep at night);
- "away": out of the village (the fields), not met anywhere;
- "square": the village square, their base location;
- "work": their workplace (the forge, the inn, the forest…), WORKING;
- any service type ("inn", "general_store"…): visiting that building.
"""

import json
import random

from sqlalchemy.orm import Session

from app.core.enums import NPCActivity
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.game.npcs import looks as npc_looks
from app.game.npcs import profile as npc_profile
from app.game.visual.npc import set_npc_stable_identity
from app.game.world.generator import generate_npc_appearance_traits, generate_npc_name

# (masculine role, feminine role, sex: "M"/"F"/None for either, age range,
#  workplace: service type, "forest", "river" or None, routine)
_WORKDAY = [[6, 8, "square"], [8, 12, "work"], [12, 13, "inn"], [13, 18, "work"],
            [18, 21, "inn"], [21, 22, "square"]]
_FIELDS = [[5, 12, "away"], [12, 13, "square"], [13, 18, "away"], [18, 20, "inn"]]
_FOREST = [[5, 11, "work"], [11, 13, "square"], [13, 17, "work"], [17, 21, "inn"]]

RESIDENTS = (
    ("aprendiz de ferreiro", "aprendiz de ferreira", None, (15, 20), "blacksmith", _WORKDAY),
    ("cozinheiro da estalagem", "cozinheira da estalagem", None, (28, 55), "inn",
     [[5, 21, "work"], [21, 22, "square"]]),
    ("lojista", "lojista", None, (30, 60), "general_store", _WORKDAY),
    ("guarda da vila", "guarda da vila", None, (22, 45), None,
     [[6, 14, "square"], [14, 15, "inn"], [15, 22, "home"]]),
    ("guarda da vila", "guarda da vila", None, (22, 45), None,
     [[6, 13, "home"], [13, 14, "inn"], [14, 22, "square"], [22, 24, "square"]]),
    ("caçador", "caçadora", None, (25, 50), "forest", _FOREST),
    ("lenhador", "lenhadora", "M", (25, 55), "forest", _FOREST),
    ("agricultor", "agricultora", "M", (30, 60), None, _FIELDS),
    ("agricultor", "agricultora", "F", (30, 60), None, _FIELDS),
    ("herbalista", "herbalista", "F", (35, 70), "river",
     [[6, 10, "work"], [10, 16, "square"], [16, 19, "home"], [19, 21, "inn"]]),
    ("velho da vila", "velha da vila", "F", (68, 85), None,
     [[7, 12, "square"], [12, 15, "home"], [15, 19, "square"], [19, 21, "inn"]]),
    ("beberrão", "beberrona", "M", (35, 60), None,
     [[10, 14, "square"], [14, 23, "inn"], [23, 24, "square"]]),
    ("rapaz curioso", "moça curiosa", None, (15, 17), None,
     [[7, 9, "home"], [9, 12, "square"], [12, 14, "notice_board"], [14, 19, "square"], [19, 21, "home"]]),
    ("carregador", "carregadora", "M", (20, 45), "merchants_guild", _WORKDAY),
    ("escrivão da guilda", "escrivã da guilda", None, (20, 50), "adventurers_guild", _WORKDAY),
)


def place_at(routine: list, hour: int) -> str:
    """Where the routine puts someone at this hour; night is home."""
    for start, end, place in routine:
        if start <= hour < end:
            return place
    return "home"


def apply_routine(db: Session, npc: NPC, hour: int) -> bool:
    """Set activity and the building visited for this hour; True if changed."""
    routine = json.loads(npc.routine_json or "[]")
    place = place_at(routine, hour)
    visiting = None
    if place in ("home", "away"):
        activity = NPCActivity.RESTING.value
    elif place == "work":
        activity = NPCActivity.WORKING.value
    elif place == "square":
        activity = NPCActivity.AVAILABLE.value
    else:
        activity = NPCActivity.AVAILABLE.value
        visiting = _service_id(db, npc.location_id, place)
    changed = (npc.activity, npc.visiting_location_id) != (activity, visiting)
    npc.activity, npc.visiting_location_id = activity, visiting
    return changed


def _service_id(db: Session, settlement_id: str, service_type: str) -> str | None:
    row = (
        db.query(Location.id)
        .filter(Location.parent_location_id == settlement_id, Location.type == service_type)
        .first()
    )
    return row[0] if row else None


def populate(
    db: Session,
    campaign_id: str,
    region_id: str,
    village: Location,
    places: dict[str, Location],
    rng: random.Random,
    used_names: set[str],
    hour: int,
) -> list[NPC]:
    """Create the residents. ``places`` maps service types plus "forest" and
    "river" to locations; a missing workplace leaves the resident in the
    square during work hours."""
    residents = []
    for male_role, female_role, sex, (low, high), workplace, routine in RESIDENTS:
        sex = sex or rng.choice(("M", "F"))
        workplace_location = places.get(workplace) if workplace else None
        if workplace and workplace_location is None:
            routine = [[start, end, "square" if place == "work" else place] for start, end, place in routine]
        npc = NPC(
            campaign_id=campaign_id,
            region_id=region_id,
            location_id=village.id,
            workplace_location_id=workplace_location.id if workplace_location else None,
            name=generate_npc_name(rng, used_names, gender=sex),
            role=male_role if sex == "M" else female_role,
            routine_json=json.dumps(routine),
        )
        db.add(npc)
        db.flush()
        _age, profile = npc_profile.generate(random.Random(f"profile:{npc.id}"), npc.role)
        npc.age = rng.randint(low, high)
        npc.profile_json = json.dumps(profile, ensure_ascii=False)
        set_npc_stable_identity(db, campaign_id, npc.id, generate_npc_appearance_traits(rng))
        npc_looks.ensure(db, npc)
        apply_routine(db, npc, hour)
        residents.append(npc)
    return residents
