"""Run the five canonical-world dialogue probes against the configured local Ollama."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.context_builder import build_context
from app.ai.llm_service import build_llm_service
from app.ai.narrator import narrate
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.world.seed import (
    create_campaign,
    grant_initial_player_knowledge,
    seed_initial_region,
)


SCENARIOS = [
    "O senhor é dessa cidade mesmo?",
    "Tem alguma estrada para o norte?",
    "Tem algum templo aqui?",
    "O que existe depois do rio?",
    "Ouvi dizer que existe um dragão nas montanhas.",
]


def main() -> None:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        campaign = create_campaign(db, "Teste manual de cânone")
        region, cardal = seed_initial_region(db, campaign.id)
        character = create_character(db, campaign.id, "Logan", region.id, cardal.id)
        grant_initial_player_knowledge(db, campaign.id, character.id)
        db.commit()
        state = build_game_state(db, campaign.id, character.id)
        base_context = build_context(db, state, active_interlocutor="Osgar Vell")
        print("=== BASE CANONICAL CONTEXT ===")
        print(base_context)
        print("=== MANUAL DIALOGUE PROBES ===")
        llm = build_llm_service()
        for index, player_input in enumerate(SCENARIOS, start=1):
            context = build_context(
                db, state, active_interlocutor="Osgar Vell", player_input=player_input
            )
            response = narrate(
                llm,
                "Logan conversa com Osgar Vell; nenhuma mudança mecânica ocorre.",
                context,
                player_input=player_input,
                recent_history="NARRATOR: Osgar Vell aguarda a próxima pergunta.",
            )
            print(f"\n[{index}] PLAYER: {player_input}")
            print(f"NARRATOR: {response}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
