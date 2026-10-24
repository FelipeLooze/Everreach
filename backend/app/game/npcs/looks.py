"""How an NPC looks, beyond hair and eye colour: height, build, hair style,
beard, skin, one distinctive mark and the clothes of their trade.

Stored in the NPC's stable visual identity (English values, which the
portrait prompt reads) and described in Portuguese for the narrator and
the player, who refers to people by what they see ("o homem da cicatriz").
Sorted once per NPC, matching age, sex and trade, seeded by the NPC's id.
"""

import random

from sqlalchemy.orm import Session

from app.game.npcs import profile as npc_profile
from app.game.visual.npc import resolve_npc_appearance, set_npc_stable_identity
from app.game.world.content_pools import NPC_HAIR_COLOR_POOL
from app.game.world.generator import gender_for_name

# English value -> (masculine, feminine) Portuguese.
_HEIGHTS = {
    "short": ("baixo", "baixa"),
    "of average height": ("de altura mediana", "de altura mediana"),
    "tall": ("alto", "alta"),
}
_BUILDS = {
    "thin": ("magro", "magra"),
    "wiry": ("esguio", "esguia"),
    "sturdy": ("robusto", "robusta"),
    "stout": ("corpulento", "corpulenta"),
    "broad-shouldered": ("de ombros largos", "de ombros largos"),
}
_ELDER_BUILDS = {
    "stooped": ("encurvado", "encurvada"),
    "frail": ("franzino", "franzina"),
    "thin": ("magro", "magra"),
    "sturdy": ("robusto", "robusta"),
}
# Strong trades never come out frail or thin.
_STRONG_ROLES = ("ferreir", "lenhador", "guarda", "agricultor", "caçador", "carregador")
_HAIR_STYLES = {
    "short hair": "curto",
    "long hair": "longo",
    "braided hair": "trançado",
    "tied-back hair": "preso atrás",
    "curly hair": "cacheado",
    "thinning hair": "ralo",
}
_BEARDS = {
    "full beard": "barba cheia",
    "short beard": "barba curta",
    "neatly trimmed beard": "barba bem aparada",
    "thick moustache": "bigode grosso",
    "clean-shaven": "",
    "stubble": "barba por fazer",
}
_SKINS = {
    "fair skin": "pele clara",
    "olive skin": "pele morena",
    "dark skin": "pele escura",
    "sun-weathered skin": "pele queimada de sol",
    "freckled skin": "pele sardenta",
}
# English -> (Portuguese phrase, the word a player would point with).
_MARKS = {
    "a scar across the chin": ("uma cicatriz no queixo", "cicatriz"),
    "a scar over one eyebrow": ("uma cicatriz na sobrancelha", "cicatriz"),
    "a crooked nose": ("o nariz torto", "nariz"),
    "a missing front tooth": ("um dente da frente faltando", "dente"),
    "thick eyebrows": ("sobrancelhas grossas", "sobrancelha"),
    "calloused hands": ("mãos calejadas", "calejad"),
    "a small gold earring": ("um brinco de ouro pequeno", "brinco"),
    "a burn mark on one hand": ("uma marca de queimadura na mão", "queimadura"),
    "deep laugh lines": ("rugas fundas de quem ri muito", "rugas"),
    "a mole on the cheek": ("uma pinta na bochecha", "pinta"),
}
_STYLE_CUES = {"trançado": "tranc", "cacheado": "cache", "longo": "longo", "curto": "curto"}
_OUTFITS = {
    "ancião": ("a worn wool mantle", "um manto de lã gasto"),
    "anciã": ("a worn wool mantle", "um manto de lã gasto"),
    "ferreir": ("a scorched leather apron", "um avental de couro chamuscado"),
    "aprendiz de ferreir": ("a scorched leather apron", "um avental de couro chamuscado"),
    "cozinheir": ("a flour-dusted apron", "um avental sujo de farinha"),
    "lojista": ("a neat apron with pockets", "um avental limpo cheio de bolsos"),
    "caçador": ("a leather jerkin and a quiver", "um gibão de couro e uma aljava"),
    "lenhador": ("a patched work shirt and a hatchet at the belt", "uma camisa remendada e uma machadinha no cinto"),
    "agricultor": ("a straw hat and muddy boots", "um chapéu de palha e botas enlameadas"),
    "herbalista": ("a satchel of dried herbs", "uma bolsa de ervas secas a tiracolo"),
    "velh": ("a faded shawl", "um xale desbotado"),
    "beberr": ("a stained, rumpled tunic", "uma túnica manchada e amarrotada"),
    "rapaz": ("a tunic too big for them", "uma túnica grande demais"),
    "moça": ("a tunic too big for them", "uma túnica grande demais"),
    "carregador": ("rolled-up sleeves and a rope over the shoulder", "mangas arregaçadas e uma corda no ombro"),
    "escriv": ("ink-stained sleeves", "mangas manchadas de tinta"),
    "estalajadeir": ("a stained cloth apron", "um avental de pano manchado"),
    "mestre da guilda de aventureiros": ("a sturdy travel coat", "um casaco de viagem resistente"),
    "mestre da guilda de comerciantes": ("a fine dyed doublet", "um gibão tingido de boa qualidade"),
    "guarda": ("a padded gambeson", "um gibão acolchoado"),
    "sacerdot": ("a plain grey robe", "um hábito cinza simples"),
}
_DEFAULT_OUTFIT = ("a simple linen tunic", "uma túnica simples de linho")
_OLD_HAIR = ("grey hair", "white hair", "silver hair")


def _outfit(role: str) -> tuple[str, str]:
    role = role.casefold()
    return next((outfit for key, outfit in _OUTFITS.items() if role.startswith(key)), _DEFAULT_OUTFIT)


def ensure(db: Session, npc) -> dict:
    """The NPC's resolved look, completed on first use."""
    traits = resolve_npc_appearance(db, npc.campaign_id, npc.id)
    if "build" in traits:
        return traits
    npc_profile.ensure(db, npc)
    rng = random.Random(f"looks:{npc.id}")
    elderly = npc.age >= 60
    strong = npc.role.casefold().startswith(_STRONG_ROLES)
    builds = [build for build in (_ELDER_BUILDS if elderly else _BUILDS)
              if not (strong and build in ("thin", "frail", "wiry", "stooped"))]
    extra = {
        "height": rng.choice(list(_HEIGHTS)),
        "build": rng.choice(builds),
        "hair_style": rng.choice(list(_HAIR_STYLES)),
        "skin": rng.choice(list(_SKINS)),
        "mark": rng.choice(list(_MARKS)),
        "outfit": _outfit(npc.role)[0],
    }
    if gender_for_name(npc.name) == "M" and npc.age >= 18:
        extra["facial_hair"] = rng.choice(list(_BEARDS) if npc.age >= 23 else ["clean-shaven", "stubble"])
    if elderly and traits.get("hair_color") not in _OLD_HAIR:
        extra["hair_color"] = rng.choice(_OLD_HAIR)
    elif npc.age < 40 and traits.get("hair_color") in _OLD_HAIR:
        # Playtest: a teenage apprentice came out with grey hair and beard.
        extra["hair_color"] = rng.choice([hair for hair in NPC_HAIR_COLOR_POOL if hair not in _OLD_HAIR])
    set_npc_stable_identity(db, npc.campaign_id, npc.id, extra)
    return {**traits, **extra}


def describe_pt(db: Session, npc, hair_pt: dict, eyes_pt: dict, *, short: bool = False) -> list[str]:
    """Portuguese pieces after the "homem"/"mulher" noun, in reading order."""
    traits = ensure(db, npc)
    feminine = gender_for_name(npc.name) == "F"
    pick = 1 if feminine else 0
    hair = hair_pt.get(traits.get("hair_color", ""), "")
    style = _HAIR_STYLES.get(traits.get("hair_style", ""), "")
    if hair and style:
        hair = f"{hair} e {style}"
    beard = _BEARDS.get(traits.get("facial_hair", ""), "")
    if beard.startswith("barba") and traits.get("hair_color") in _OLD_HAIR:
        beard = f"{beard} {'branca' if traits['hair_color'] == 'white hair' else 'grisalha'}"
    mark = f"com {_MARKS[traits['mark']][0]}" if traits.get("mark") in _MARKS else ""
    if short:
        return [piece for piece in (hair, beard, mark) if piece]
    pieces = [
        f"{_HEIGHTS[traits['height']][pick]} e {(_ELDER_BUILDS | _BUILDS)[traits['build']][pick]}",
        hair,
        beard,
        eyes_pt.get(traits.get("eye_color", ""), ""),
        _SKINS.get(traits.get("skin", ""), ""),
        mark,
        f"usa {_outfit(npc.role)[1]}",
    ]
    return [piece for piece in pieces if piece]


def cues_pt(db: Session, npc) -> list[str]:
    """Words a player would use to point at this NPC: the beard, the hair
    style and the core noun of the distinctive mark."""
    traits = ensure(db, npc)
    cues = []
    beard = _BEARDS.get(traits.get("facial_hair", ""), "")
    if beard:
        cues.append(beard.split()[0])  # "barba" / "bigode"
    style = _HAIR_STYLES.get(traits.get("hair_style", ""), "")
    if style in _STYLE_CUES:
        cues.append(_STYLE_CUES[style])
    if traits.get("mark") in _MARKS:
        cues.append(_MARKS[traits["mark"]][1])
    return cues
