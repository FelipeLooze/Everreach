"""Ties between the people of the starting village: family, master and
apprentice, friends and rivals.

Starting village, part 3 (2026-10-24). The ties are fixed by role (the
farming couple and their teenager, the woodcutter father of the forge
apprentice…); names, sex and age come from part 2. Family shares a surname
and the ages add up. Everyone in the village knows these ties, so any NPC
can talk about the others, and the narrator stops inventing relatives.
"""

from sqlalchemy.orm import Session

from app.db.models.npc import NPC
from app.db.models.npc_bond import NPCBond
from app.game.world.generator import gender_for_name

PARENT, SPOUSES, SIBLINGS, MASTER, FRIENDS, RIVALS = (
    "PARENT", "SPOUSES", "SIBLINGS", "MASTER", "FRIENDS", "RIVALS",
)
_FAMILY = (PARENT, SPOUSES, SIBLINGS)
MAX_VILLAGE_LINES = 12
_MUTUAL_PT = {SPOUSES: "casados", SIBLINGS: "irmãos", FRIENDS: "amigos", RIVALS: "rivais"}

# Word for the other person, as seen from this side: (kind, I am first?) -> (masc, fem).
_WORD = {
    (PARENT, True): ("filho", "filha"),
    (PARENT, False): ("pai", "mãe"),
    (SPOUSES, True): ("marido", "esposa"),
    (SPOUSES, False): ("marido", "esposa"),
    (SIBLINGS, True): ("irmão", "irmã"),
    (SIBLINGS, False): ("irmão", "irmã"),
    (MASTER, True): ("aprendiz", "aprendiz"),
    (MASTER, False): ("mestre", "mestra"),
    (FRIENDS, True): ("amigo", "amiga"),
    (FRIENDS, False): ("amigo", "amiga"),
    (RIVALS, True): ("rival", "rival"),
    (RIVALS, False): ("rival", "rival"),
}


def _word(kind: str, viewer_is_first: bool, other: NPC) -> str:
    masc, fem = _WORD[(kind, viewer_is_first)]
    return fem if gender_for_name(other.name) == "F" else masc


def _rename(npc: NPC, family_name: str) -> None:
    npc.name = f"{npc.name.split(' ', 1)[0]} {family_name}"


def _family_name(npc: NPC) -> str:
    return npc.name.split(" ", 1)[1] if " " in npc.name else npc.name


def link_starting_village(db: Session, campaign_id: str, settlement_id: str) -> list[NPCBond]:
    people = db.query(NPC).filter(NPC.campaign_id == campaign_id, NPC.location_id == settlement_id).all()

    def first(*prefixes: str) -> NPC | None:
        return next((npc for npc in people for prefix in prefixes if npc.role.startswith(prefix)), None)

    def every(prefix: str) -> list[NPC]:
        return [npc for npc in people if npc.role.startswith(prefix)]

    bonds: list[NPCBond] = []

    def bond(kind: str, a: NPC | None, b: NPC | None, note: str = "") -> None:
        if a is not None and b is not None and a is not b:
            bonds.append(NPCBond(campaign_id=campaign_id, settlement_id=settlement_id,
                                 first_npc_id=a.id, second_npc_id=b.id, kind=kind, note=note))

    def parent_of(parent: NPC | None, child: NPC | None) -> None:
        if parent is None or child is None:
            return
        parent.age = max(parent.age or 0, (child.age or 0) + 20)
        _rename(child, _family_name(parent))
        bond(PARENT, parent, child)

    farmers = sorted(every("agricultor"), key=lambda npc: gender_for_name(npc.name) != "M")
    teen = first("rapaz curioso", "moça curiosa")
    if len(farmers) == 2:
        husband, wife = farmers
        _rename(wife, _family_name(husband))
        bond(SPOUSES, husband, wife)
        parent_of(husband, teen)
        parent_of(wife, teen)

    woodcutter, apprentice = first("lenhador"), first("aprendiz")
    parent_of(woodcutter, apprentice)
    bond(MASTER, first("ferreir"), apprentice)

    innkeeper, cook = first("estalajadeir"), first("cozinheir")
    if innkeeper is not None and cook is not None:
        _rename(cook, _family_name(innkeeper))
        bond(SPOUSES if gender_for_name(cook.name) != gender_for_name(innkeeper.name) else SIBLINGS,
             innkeeper, cook)

    guards = every("guarda")
    if len(guards) == 2:
        _rename(guards[1], _family_name(guards[0]))
        bond(SIBLINGS, guards[0], guards[1])

    old_one = first("velho da vila", "velha da vila")
    bond(FRIENDS, first("ancião", "anciã"), old_one)
    bond(FRIENDS, first("herbalista"), old_one)
    bond(FRIENDS, first("beberr"), woodcutter)
    bond(FRIENDS, first("caçador"), first("escriv"))

    bond(RIVALS, first("caçador"), woodcutter,
         "o lenhador derruba as árvores justo onde se armam as armadilhas, e os dois discutem por isso")
    bond(RIVALS, first("lojista"), first("mestre da guilda de comerciantes"),
         "a loja acha que a guilda dita os preços e sufoca o comércio pequeno")

    db.add_all(bonds)
    db.flush()
    return bonds


def _bonds_of(db: Session, npc: NPC) -> list[NPCBond]:
    return (
        db.query(NPCBond)
        .filter((NPCBond.first_npc_id == npc.id) | (NPCBond.second_npc_id == npc.id))
        .all()
    )


def _who(npc: NPC) -> str:
    return f"{npc.name} ({npc.role})"


def context_lines(db: Session, npc: NPC) -> list[str]:
    """What the active NPC knows of ties: their own, then the village's."""
    own = []
    has_family = False
    for tie in _bonds_of(db, npc):
        viewer_first = tie.first_npc_id == npc.id
        other = db.get(NPC, tie.second_npc_id if viewer_first else tie.first_npc_id)
        has_family = has_family or tie.kind in _FAMILY
        note = f" — {tie.note}" if tie.note else ""
        own.append(f"- {_word(tie.kind, viewer_first, other)}: {_who(other)}{note}")
    lines = []
    if own:
        lines += ["Their own ties (real — they may talk about them):", *own]
    if not has_family:
        lines.append("Family: none — they live alone and never had any; they mention no relatives, "
                     "living or dead.")
    else:
        lines.append("They have no other relatives than those listed, living or dead.")

    village = (
        db.query(NPCBond)
        .filter(
            NPCBond.campaign_id == npc.campaign_id,
            NPCBond.settlement_id == npc.location_id,
            NPCBond.first_npc_id != npc.id,
            NPCBond.second_npc_id != npc.id,
        )
        .limit(MAX_VILLAGE_LINES)
        .all()
    )
    if village:
        lines.append(
            "Ties between villagers — these are ALL of them; never invent others (no other "
            "relatives, grandchildren, couples, feuds or vices); a shared surname means nothing "
            "unless a tie is listed. Mention them only if asked or it fits naturally:"
        )
        for tie in village:
            a, b = db.get(NPC, tie.first_npc_id), db.get(NPC, tie.second_npc_id)
            note = f" — {tie.note}" if tie.note else ""
            lines.append(f"- {_who(a)} é {_word(tie.kind, False, a)} de {_who(b)}{note}"
                         if tie.kind in (PARENT, MASTER)
                         else f"- {_who(a)} e {_who(b)} são {_MUTUAL_PT[tie.kind]}{note}")
    return lines
