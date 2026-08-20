import unicodedata
from dataclasses import dataclass

from app.core.enums import EarthProfession


@dataclass(frozen=True)
class BackgroundProfessionAffinity:
    earth_profession: EarthProfession
    background_label: str
    profession_key: str
    profession_name: str
    match_terms: tuple[str, ...]


BACKGROUND_PROFESSION_AFFINITIES = {
    EarthProfession.CHEF: BackgroundProfessionAffinity(
        EarthProfession.CHEF,
        "Chef profissional na Terra",
        "CULINARY",
        "Culinária",
        ("chef", "cozinheir", "cook"),
    ),
    EarthProfession.FARMER: BackgroundProfessionAffinity(
        EarthProfession.FARMER,
        "Agricultor profissional na Terra",
        "AGRICULTURE",
        "Agricultura",
        ("agricult", "fazendeir", "farmer"),
    ),
    EarthProfession.CARPENTER: BackgroundProfessionAffinity(
        EarthProfession.CARPENTER,
        "Carpinteiro profissional na Terra",
        "CARPENTRY",
        "Carpintaria",
        ("carpinteir", "carpenter"),
    ),
    EarthProfession.BLACKSMITH: BackgroundProfessionAffinity(
        EarthProfession.BLACKSMITH,
        "Ferreiro profissional na Terra",
        "BLACKSMITHING",
        "Ferraria",
        ("ferreir", "blacksmith"),
    ),
}


def affinity_for_earth_profession(
    earth_profession: EarthProfession | None,
) -> BackgroundProfessionAffinity | None:
    if earth_profession is None:
        return None
    return BACKGROUND_PROFESSION_AFFINITIES.get(earth_profession)


def affinity_supported_by_background(
    background: str,
    earth_profession: EarthProfession | None,
) -> BackgroundProfessionAffinity | None:
    affinity = affinity_for_earth_profession(earth_profession)
    if affinity is None:
        return None
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", background.lower())
        if not unicodedata.combining(character)
    )
    if not any(term in normalized for term in affinity.match_terms):
        return None
    return affinity
