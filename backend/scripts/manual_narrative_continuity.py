"""Exercise a three-turn conversation through the real engine and configured Ollama."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.llm_service import build_llm_service
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.core.enums import MemoryOwnerType
from app.db.models.memory import Memory
from app.db.models.relationship import CharacterNPCRelationship
from app.game import engine
from app.game.character.service import create_character
from app.game.npcs.service import get_active_interlocutor
from app.game.world.seed import create_campaign, seed_initial_region
from app.services.story_log import get_recent_story_log


PLAYER_INPUTS = (
    "Falo com Osgar: — Bom dia.",
    "— O senhor nasceu aqui?",
    "— E conhece bem esta vila?",
)


def main() -> None:
    database = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(database, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(database)
    db = sessionmaker(bind=database)()
    try:
        campaign = create_campaign(db, "Teste manual de continuidade")
        region, cardal = seed_initial_region(db, campaign.id)
        character = create_character(db, campaign.id, "Logan", region.id, cardal.id)
        db.commit()
        llm = build_llm_service()

        for player_input in PLAYER_INPUTS:
            result = engine.resolve_action(
                db, llm, campaign.id, character.id, player_input
            )
            active_npc = get_active_interlocutor(
                db, campaign.id, character.id, character.location_id
            )
            print(f"PLAYER: {player_input}")
            print(f"NARRATOR: {result.narrative}")
            print(f"ACTIVE NPC: {active_npc.name if active_npc else 'none'}\n")
            relationship = db.query(CharacterNPCRelationship).one()
            player_memory_count = (
                db.query(Memory)
                .filter(
                    Memory.owner_type == MemoryOwnerType.PLAYER.value,
                    Memory.owner_id == character.id,
                )
                .count()
            )
            print(
                f"RELATIONSHIP: familiarity={relationship.familiarity}, "
                f"trust={relationship.trust}, affinity={relationship.affinity}"
            )
            print(f"PLAYER MEMORIES: {player_memory_count}\n")

        story = get_recent_story_log(db, campaign.id, character.id)
        assert [entry.text for entry in story[-6:]] == [
            item
            for exchange in zip(
                PLAYER_INPUTS,
                [entry.text for entry in story if entry.kind == "narrator"][-3:],
            )
            for item in exchange
        ]
        assert get_active_interlocutor(
            db, campaign.id, character.id, character.location_id
        ) is not None
        relationship = db.query(CharacterNPCRelationship).one()
        assert relationship.familiarity == 3
        assert (
            db.query(Memory)
            .filter(
                Memory.owner_type == MemoryOwnerType.PLAYER.value,
                Memory.owner_id == character.id,
            )
            .count()
            == 4
        )
        assert (
            db.query(Memory)
            .filter(
                Memory.owner_type == MemoryOwnerType.NPC.value,
                Memory.owner_id == get_active_interlocutor(
                    db, campaign.id, character.id, character.location_id
                ).id,
            )
            .count()
            == 4
        )
        print(
            "OK: entrada, histórico, memória, relação e interlocutor permaneceram "
            "consistentes por três turnos."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
