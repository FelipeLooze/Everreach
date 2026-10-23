"""Can the game tell who the player means, from what the narrator described?

Builds fresh worlds and visits the arrival square and every workplace during
working hours. For every native there it writes the phrasings a player would
use after reading the scene — appearance only, never the name or role the
player can't know yet — and runs each through the REAL intent model. A
phrase passes only when the engine registered a conversation with that exact
person, or asked "com quem?" when the description fits more than one person
present. The narrator is stubbed: identification is what's measured.

usage (from backend/, DATABASE_URL pointing at a scratch DB):
    python scripts/reference_battery.py [worlds=2]
"""
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

from app.ai.llm_service import LLMService, build_role_llm_services
from app.ai.people_present import npc_appearance_pt
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models.character import Character
from app.db.models.npc import NPC
from app.game import engine
from app.game.game_state import build_game_state
from app.game.players.appearance import ensure_transported_features
from app.game.time import clock
from app.main import app

DAY = 24 * 60


class QuietNarrator(LLMService):
    def __init__(self):
        self.turn = 0

    def generate(self, system, prompt):
        self.turn += 1
        return f"A cena segue ({self.turn})."


def phrasings(looks: str) -> list[str]:
    """looks: "homem idoso, cabelo branco, olhos azuis"."""
    who, *features = [part.strip() for part in looks.split(",")]
    article = "a" if who.startswith("mulher") else "o"
    of = "da" if article == "a" else "do"
    hair = next((feature for feature in features if feature.startswith("cabelo")), None)
    eyes = next((feature for feature in features if feature.startswith("olhos")), None)
    noun = {"homem idoso": "senhor", "mulher idosa": "senhora"}.get(who, who)
    lines = []
    if hair:
        lines.append(f'Vou falar com {article} {noun} de {hair}: "Bom dia! Tudo bem?"')
        lines.append(f"Me aproximo {of} {who} de {hair} e cumprimento.")
    if eyes:
        lines.append(f'Falo com {article} {who} de {eyes}: "Olá, posso perguntar uma coisa?"')
    return lines


def transported_phrasings(features: str) -> tuple[str, list[str]]:
    """features: "Mulher jovem, alta e magra, de cabelo preto e olhos azuis."
    Returns the look a player can tell apart (sex + hair) and phrasings."""
    noun = "mulher" if features.startswith("Mulher") else "homem"
    article = "a" if noun == "mulher" else "o"
    hair = re.search(r"de (cabelo .+?) e olhos", features)
    hair = hair.group(1) if hair else "cabelo escuro"
    return f"{noun}, {hair}", [
        f'Falo com {article} {noun} de {hair} que chegou comigo: "Oi, tudo bem com você?"',
        f"Vou até {article} {noun} de {hair} entre os recém-chegados e pergunto o nome.",
    ]


def _set_hour(db, campaign_id: str, hour: int) -> None:
    now = clock.get_world_time(db, campaign_id).total_minutes()
    target = (now // DAY + 1) * DAY + hour * 60
    clock.advance_world_time(db, campaign_id, target - now)


def main(worlds: int) -> None:
    intent_service, _ = build_role_llm_services(get_settings())
    narrator = QuietNarrator()
    client = TestClient(app)
    results = []
    for world in range(worlds):
        cid = client.post("/api/campaigns", json={"name": f"Bateria {world}"}).json()["id"]
        chid = client.post(f"/api/campaigns/{cid}/characters", json={"name": "Logan"}).json()["id"]
        client.post(f"/api/campaigns/{cid}/start", params={"character_id": chid})
        db = SessionLocal()
        character = db.get(Character, chid)
        _set_hour(db, cid, 10)
        db.commit()
        square = character.location_id
        workplaces = sorted({
            npc.workplace_location_id for npc in db.query(NPC).filter(NPC.campaign_id == cid)
            if npc.workplace_location_id
        })
        for place in [square, *workplaces]:
            character.location_id = place
            db.commit()
            state = build_game_state(db, cid, chid)
            if not state.nearby_npcs:
                continue
            looks = {npc.id: npc_appearance_pt(db, cid, npc) for npc in state.nearby_npcs}
            print(f"\n--- {state.location.name}: {len(state.nearby_npcs)} nativos, "
                  f"{len(state.nearby_simulated_players)} transportados", flush=True)
            for npc in state.nearby_npcs:
                same_look = [other for other, look in looks.items() if look == looks[npc.id]]
                for text in phrasings(looks[npc.id]):
                    started = time.monotonic()
                    result = engine.resolve_action(db, narrator, cid, chid, text, intent_llm_service=intent_service)
                    db.commit()
                    talked_to = [
                        other for other in state.nearby_npcs
                        if f"conversa com {other.name}" in result.mechanical_summary
                    ]
                    asked = result.mechanical_summary.startswith(engine.WHO_DO_YOU_MEAN_PREFIX)
                    if len(same_look) > 1:
                        ok = asked or (len(talked_to) == 1 and talked_to[0].id in same_look)
                    else:
                        ok = [other.id for other in talked_to] == [npc.id]
                    results.append(ok)
                    print(
                        f"{'OK ' if ok else 'ERR'} {time.monotonic() - started:4.1f}s | {looks[npc.id]:<42} | {text}\n"
                        f"      -> {result.mechanical_summary[:140]}",
                        flush=True,
                    )
            # The transported strangers standing here, told apart only by
            # what the narrator can describe: sex and hair.
            people = state.nearby_simulated_players
            looks_by_player = {
                player.id: transported_phrasings(ensure_transported_features(db, player)) for player in people
            }
            for player in people:
                look, lines = looks_by_player[player.id]
                same = [other for other, (other_look, _) in looks_by_player.items() if other_look == look]
                for text in lines:
                    started = time.monotonic()
                    result = engine.resolve_action(db, narrator, cid, chid, text, intent_llm_service=intent_service)
                    db.commit()
                    talked = [other for other in people if f"conversa com {other.name}" in result.mechanical_summary]
                    asked = result.mechanical_summary.startswith(engine.WHO_DO_YOU_MEAN_PREFIX)
                    if len(same) > 1:
                        ok = asked or (len(talked) == 1 and talked[0].id in same)
                    else:
                        ok = [other.id for other in talked] == [player.id]
                    results.append(ok)
                    print(
                        f"{'OK ' if ok else 'ERR'} {time.monotonic() - started:4.1f}s | {look:<42} | {text}\n"
                        f"      -> {result.mechanical_summary[:140]}",
                        flush=True,
                    )
        db.close()
    print(f"\n{sum(results)}/{len(results)} identificações corretas")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
