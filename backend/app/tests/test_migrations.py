from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import enable_sqlite_foreign_keys
from app.game.world.seed import create_campaign


def test_alembic_builds_a_readable_sqlite_database_from_scratch(tmp_path, monkeypatch):
    database_path = tmp_path / "migration-test.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    backend_root = Path(__file__).parents[2]

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))

    try:
        command.upgrade(config, "head")

        engine = create_engine(database_url)
        event.listen(engine, "connect", enable_sqlite_foreign_keys)
        tables = set(inspect(engine).get_table_names())
        assert {
            "campaigns",
            "characters",
            "regions",
            "locations",
            "world_developments",
            "world_times",
            "world_events",
            "character_npc_relationships",
            "simulated_player_relationships",
            "simulated_player_groups",
            "simulated_player_group_members",
            "simulated_player_skills",
        }.issubset(tables)
        fact_constraints = {
            item["name"] for item in inspect(engine).get_unique_constraints("knowledge_facts")
        }

        fact_columns = {
            item["name"]
            for item in inspect(engine).get_columns(
                "knowledge_facts"
            )
        }

        knower_constraints = {
            item["name"] for item in inspect(engine).get_unique_constraints("knowledge_knowers")
        }
        connection_indexes = {
            item["name"] for item in inspect(engine).get_indexes("location_connections")
        }
        development_indexes = {
            item["name"]
            for item in inspect(engine).get_indexes(
                "world_developments"
            )
        }
        npc_indexes = {
            item["name"]
            for item in inspect(engine).get_indexes("npcs")
        }
        simulated_player_indexes = {
            item["name"]
            for item in inspect(engine).get_indexes("simulated_players")
        }
        simulated_player_columns = {
            item["name"]
            for item in inspect(engine).get_columns("simulated_players")
        }
        assert "uq_knowledge_fact_campaign_key" in fact_constraints
        assert "social_priority" in fact_columns
        assert "uq_knowledge_knower_fact_identity" in knower_constraints
        assert "ix_location_connection_origin_active" in connection_indexes
        event_columns = {item["name"] for item in inspect(engine).get_columns("world_events")}
        memory_columns = {item["name"] for item in inspect(engine).get_columns("memories")}
        assert "importance" in event_columns
        assert {"owner_type", "owner_id", "subject", "source_event_id"}.issubset(
            memory_columns
        )
        assert (
            "ix_world_developments_campaign_status_next_update"
            in development_indexes
        )
        assert "ix_npcs_campaign_location_alive" in npc_indexes
        assert (
            "ix_simulated_players_campaign_location_status"
            in simulated_player_indexes
        )
        assert {"xp", "risk_tolerance"}.issubset(simulated_player_columns)

        with Session(engine) as session:
            campaign = create_campaign(session, "Banco migrado")
            session.commit()
            campaign_id = campaign.id

        with Session(engine) as session:
            from app.db.models.campaign import Campaign

            stored = session.get(Campaign, campaign_id)
            assert stored is not None
            assert stored.name == "Banco migrado"

        command.downgrade(config, "base")
        assert "campaigns" not in set(inspect(engine).get_table_names())
        engine.dispose()
    finally:
        get_settings.cache_clear()
