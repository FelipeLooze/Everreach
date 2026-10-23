"""A transported person's own looks, registered once and kept.

Everyone arrives in the same outfit, and the physical description was empty
for every transported person, so the narrator invented one ("uma mulher de
cabelos escuros, um homem de ombros largos") that the engine knew nothing
about — the player then referred to them by it and nobody resolved. The
features are generated deterministically from the person's id, stored the
first time they are needed, and never change.
"""

import random

from sqlalchemy.orm import Session

from app.db.models.simulated_player import SimulatedPlayer
from app.game.world.content_pools import NPC_EYE_COLOR_POOL
from app.game.world.generator import gender_for_name

_HAIR_PT = (
    "cabelo preto", "cabelo castanho-escuro", "cabelo castanho", "cabelo ruivo",
    "cabelo loiro", "cabelo crespo e escuro", "cabelo raspado",
)
_EYES_PT = {
    "brown eyes": "olhos castanhos", "blue eyes": "olhos azuis", "green eyes": "olhos verdes",
    "hazel eyes": "olhos cor de mel", "grey eyes": "olhos cinzentos", "amber eyes": "olhos âmbar",
}
_AGES = ("jovem", "de uns vinte e poucos anos", "de meia-idade", "de uns trinta anos")
_HEIGHTS = ("alto", "baixo", "de estatura mediana")
_BUILDS = ("magro", "robusto", "de ombros largos", "esguio")


def ensure_transported_features(db: Session, player: SimulatedPlayer) -> str:
    if player.physical_description:
        return player.physical_description
    rng = random.Random(player.id)
    gender = gender_for_name(player.name) or rng.choice(("M", "F"))
    noun = "Homem" if gender == "M" else "Mulher"
    feminine = gender == "F"

    def agree(word: str) -> str:
        if not feminine:
            return word
        return {"alto": "alta", "baixo": "baixa", "magro": "magra", "robusto": "robusta",
                "esguio": "esguia"}.get(word, word)

    player.physical_description = (
        f"{noun} {rng.choice(_AGES)}, {agree(rng.choice(_HEIGHTS))} e {agree(rng.choice(_BUILDS))}, "
        f"de {rng.choice(_HAIR_PT)} e {_EYES_PT[rng.choice(NPC_EYE_COLOR_POOL)]}."
    )
    db.flush()
    return player.physical_description
