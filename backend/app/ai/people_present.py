"""The people in the scene, described the same way for everyone.

The narrator describes strangers by appearance (the player knows no names or
roles yet) and the player then refers to them by that description ("o homem
de barba branca"). Before this module the narrator invented the appearance
and the engine matched only names and roles, so the player's natural
reference resolved nobody. Now the narrator receives each person's
registered appearance, and the intent parser picks the person the player
means from the same numbered list (P1, P2…) — no word list to maintain.
"""

import re
import unicodedata

from sqlalchemy.orm import Session

from app.game.players.appearance import ensure_transported_features
from app.game.visual.npc import resolve_npc_appearance
from app.game.world.generator import gender_for_name

_HAIR_PT = {
    "black hair": "cabelo preto",
    "dark brown hair": "cabelo castanho-escuro",
    "brown hair": "cabelo castanho",
    "auburn hair": "cabelo ruivo-acobreado",
    "blonde hair": "cabelo loiro",
    "grey hair": "cabelo grisalho",
    "silver hair": "cabelo prateado",
    "red hair": "cabelo ruivo",
    "white hair": "cabelo branco",
}
_EYES_PT = {
    "brown eyes": "olhos castanhos",
    "blue eyes": "olhos azuis",
    "green eyes": "olhos verdes",
    "hazel eyes": "olhos cor de mel",
    "grey eyes": "olhos cinzentos",
    "amber eyes": "olhos âmbar",
}
_ELDER_ROLES = ("ancião", "anciã")


def npc_appearance_pt(db: Session, campaign_id: str, npc) -> str:
    traits = resolve_npc_appearance(db, campaign_id, npc.id)
    gender = gender_for_name(npc.name)
    elderly = npc.role.casefold().startswith(_ELDER_ROLES)
    who = {
        ("M", True): "homem idoso", ("F", True): "mulher idosa",
        ("M", False): "homem", ("F", False): "mulher",
    }.get((gender, elderly), "pessoa idosa" if elderly else "pessoa")
    features = [
        _HAIR_PT.get(traits.get("hair_color", ""), ""),
        _EYES_PT.get(traits.get("eye_color", ""), ""),
    ]
    return ", ".join([who, *(feature for feature in features if feature)])


def present_people(state) -> list[tuple[str, object]]:
    """Everyone the player could address here, in a fixed order: P1, P2…"""
    return [("npc", npc) for npc in state.nearby_npcs] + [
        ("simulated_player", player) for player in state.nearby_simulated_players
    ]


def people_present_lines(db: Session, state, *, active_npc_id=None, active_player_id=None) -> list[str]:
    lines = ["PESSOAS PRESENTES"]
    for index, (kind, person) in enumerate(present_people(state), start=1):
        if kind == "npc":
            looks = npc_appearance_pt(db, state.character.campaign_id, person)
            who = f"{person.name}, {person.role}"
            talking = active_npc_id == person.id
        else:
            # Their own looks; the outfit is the same for every transported.
            looks = f"{ensure_transported_features(db, person)} Traje dos Transportados."
            who = f"{person.name}, transportado"
            talking = active_player_id == person.id
        lines.append(f"- P{index}: {who} — {looks}{' — em conversa com o jogador agora' if talking else ''}")
    if len(lines) == 1:
        lines.append("- ninguém")
    return lines


_FEMININE_WORDS = ("mulher", "senhora", "moca", "garota", "velha", "idosa", "menina", "dama")
_MASCULINE_WORDS = ("homem", "senhor", "rapaz", "garoto", "velho", "idoso", "menino", "sujeito", "cara")


def _plain(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", (text or "").casefold())
        if not unicodedata.combining(char)
    )


def match_by_appearance(db: Session, state, raw_text: str):
    """Instant backstop when the parser named nobody: the hair the player
    mentioned ("a mulher de cabelo preto"), plus sex when stated, against
    each person's registered look. Exactly one match or nothing."""
    text = _plain(raw_text)
    wants_female = any(word in text.split() for word in _FEMININE_WORDS)
    wants_male = any(word in text.split() for word in _MASCULINE_WORDS)
    matches = []
    for kind, person in present_people(state):
        if kind == "npc":
            looks = npc_appearance_pt(db, state.character.campaign_id, person)
        else:
            looks = ensure_transported_features(db, person)
        looks = _plain(looks)
        hair = next(iter(re.findall(r"cabelo [a-z-]+(?: e [a-z]+)?", looks)), None)
        if hair is None or hair not in text:
            continue
        female = looks.startswith("mulher")
        if (wants_female and not female) or (wants_male and female):
            continue
        matches.append((kind, person))
    return matches[0] if len(matches) == 1 else None


def person_for_ref(state, ref: str | None):
    """(kind, person) for "P2", or None when the ref names no one present."""
    if not ref or not ref.upper().startswith("P") or not ref[1:].isdigit():
        return None
    people = present_people(state)
    index = int(ref[1:]) - 1
    return people[index] if 0 <= index < len(people) else None


_INTENT_SECTIONS = (
    "CURRENT PLAYER",
    "RELEVANT INVENTORY AND EQUIPMENT",
    "CONNECTED LOCATIONS KNOWN TO PLAYER",
    "PLAYER CURRENT LOCATION KNOWLEDGE",
    "KNOWN ORGANIZATIONS",
    "NEARBY SHOPS",
    "ACTIVE QUESTS",
    "KNOWN TECHNIQUES",
    "ACTIVE COMBAT PARTICIPANTS",
)


def build_intent_context(db: Session, state, narrator_context: str, *, active_npc_id=None, active_player_id=None) -> str:
    """What the intent parser needs, without the narrator's memories,
    knowledge and canon notes: about a third of the size, which keeps the
    call under Groq's free per-minute token budget (going over fell back to
    a model ten times slower) and gives it the numbered people list."""
    blocks = [
        block for block in narrator_context.split("\n\n")
        if block.split("\n", 1)[0].strip().startswith(_INTENT_SECTIONS)
    ]
    people = "\n".join(
        people_present_lines(db, state, active_npc_id=active_npc_id, active_player_id=active_player_id)
    )
    return "\n\n".join([people, *blocks])
