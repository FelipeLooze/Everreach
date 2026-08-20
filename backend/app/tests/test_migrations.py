from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
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
            "professions",
            "character_professions",
            "class_definitions",
            "character_class_offers",
            "domain_definitions",
            "character_domain_evidence",
            "domain_evidence_records",
            "character_domain_synergies",
            "domain_synergy_records",
            "class_definition_domains",
            "attribute_definitions",
            "attribute_evidence_records",
            "character_resource_growth",
            "resource_growth_evidence_records",
            "applied_progression_outcomes",
            "technique_domains",
            "technique_use_records",
            "combat_encounters",
            "combat_participants",
            "combat_turns",
            "combat_actions",
            "combat_conditions",
            "combat_technique_profiles",
            "combat_tactical_actions",
            "combat_autonomous_decisions",
            "character_recoveries",
        }.issubset(tables)
        combat_encounter_columns = {
            item["name"] for item in inspect(engine).get_columns("combat_encounters")
        }
        combat_participant_columns = {
            item["name"] for item in inspect(engine).get_columns("combat_participants")
        }
        assert "current_turn_order" in combat_encounter_columns
        assert {
            "initiative_roll",
            "initiative_modifier",
            "initiative_score",
            "turn_order",
        }.issubset(combat_participant_columns)
        combat_action_columns = {
            item["name"] for item in inspect(engine).get_columns("combat_actions")
        }
        combat_action_constraints = {
            item["name"]
            for item in inspect(engine).get_unique_constraints("combat_actions")
        }
        assert {
            "turn_id",
            "actor_participant_id",
            "target_participant_id",
            "action_key",
            "action_type",
            "attack_roll",
            "attack_total",
            "defense_total",
            "outcome",
            "damage_roll",
            "damage_total",
            "target_hp_before",
            "target_hp_after",
            "lethal",
            "resource_key",
            "resource_cost",
            "resource_before",
            "resource_after",
            "technique_id",
            "base_damage_dice",
            "damage_die_sides",
            "damage_attribute",
        }.issubset(combat_action_columns)
        assert {
            "uq_combat_action_key",
            "uq_combat_action_turn",
        }.issubset(combat_action_constraints)
        combat_tactical_columns = {
            item["name"]
            for item in inspect(engine).get_columns("combat_tactical_actions")
        }
        combat_tactical_constraints = {
            item["name"]
            for item in inspect(engine).get_unique_constraints(
                "combat_tactical_actions"
            )
        }
        combat_tactical_indexes = {
            item["name"]
            for item in inspect(engine).get_indexes("combat_tactical_actions")
        }
        assert {
            "encounter_id",
            "turn_id",
            "actor_participant_id",
            "target_participant_id",
            "action_key",
            "action_type",
            "resource_key",
            "resource_cost",
            "resource_before",
            "resource_after",
            "previous_range_band",
            "new_range_band",
            "roll",
            "modifier",
            "total",
            "dc",
            "success",
            "created_world_minute",
        }.issubset(combat_tactical_columns)
        assert {
            "uq_combat_tactical_action_key",
            "uq_combat_tactical_action_turn",
        }.issubset(combat_tactical_constraints)
        assert (
            "ix_combat_tactical_action_encounter_time"
            in combat_tactical_indexes
        )
        autonomous_decision_columns = {
            item["name"]
            for item in inspect(engine).get_columns(
                "combat_autonomous_decisions"
            )
        }
        autonomous_decision_constraints = {
            item["name"]
            for item in inspect(engine).get_unique_constraints(
                "combat_autonomous_decisions"
            )
        }
        autonomous_decision_indexes = {
            item["name"]
            for item in inspect(engine).get_indexes(
                "combat_autonomous_decisions"
            )
        }
        assert {
            "encounter_id",
            "turn_id",
            "actor_participant_id",
            "target_participant_id",
            "combat_action_id",
            "tactical_action_id",
            "decision_key",
            "decision_kind",
            "action_type",
            "reason",
            "risk_tolerance",
            "hp_ratio",
            "stamina_ratio",
            "created_world_minute",
        }.issubset(autonomous_decision_columns)
        assert {
            "uq_combat_autonomous_decision_key",
            "uq_combat_autonomous_decision_turn",
        }.issubset(autonomous_decision_constraints)
        assert (
            "ix_combat_autonomous_decision_encounter_time"
            in autonomous_decision_indexes
        )
        combat_condition_columns = {
            item["name"]
            for item in inspect(engine).get_columns("combat_conditions")
        }
        combat_condition_constraints = {
            item["name"]
            for item in inspect(engine).get_unique_constraints("combat_conditions")
        }
        combat_condition_indexes = {
            item["name"]
            for item in inspect(engine).get_indexes("combat_conditions")
        }
        assert {
            "participant_id",
            "source_action_id",
            "application_key",
            "condition_type",
            "remaining_turns",
            "active",
            "removal_reason",
            "source_tactical_action_id",
        }.issubset(combat_condition_columns)
        assert "uq_combat_condition_application" in combat_condition_constraints
        assert (
            "ix_combat_condition_participant_active"
            in combat_condition_indexes
        )
        recovery_columns = {
            item["name"]
            for item in inspect(engine).get_columns("character_recoveries")
        }
        recovery_constraints = {
            item["name"]
            for item in inspect(engine).get_unique_constraints(
                "character_recoveries"
            )
        }
        recovery_indexes = {
            item["name"]
            for item in inspect(engine).get_indexes("character_recoveries")
        }
        assert {
            "campaign_id",
            "character_id",
            "recovery_key",
            "recovery_type",
            "duration_minutes",
            "started_world_minute",
            "hp_before",
            "hp_after",
            "mana_before",
            "mana_after",
            "stamina_before",
            "stamina_after",
        }.issubset(recovery_columns)
        assert "uq_character_recovery_key" in recovery_constraints
        assert "ix_character_recovery_campaign_time" in recovery_indexes
        combat_technique_columns = {
            item["name"]
            for item in inspect(engine).get_columns("combat_technique_profiles")
        }
        assert {
            "technique_id",
            "action_type",
            "attack_attribute",
            "resource_key",
            "resource_cost",
            "base_damage_dice",
            "damage_die_sides",
            "damage_attribute",
            "condition_type",
            "condition_duration_turns",
        } == combat_technique_columns
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
        character_columns = {
            item["name"]
            for item in inspect(engine).get_columns("characters")
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
        npc_columns = {
            item["name"] for item in inspect(engine).get_columns("npcs")
        }
        assert {
            "hp_current",
            "hp_max",
            "mana_current",
            "mana_max",
            "stamina_current",
            "stamina_max",
        }.issubset(npc_columns)
        assert (
            "ix_simulated_players_campaign_location_status"
            in simulated_player_indexes
        )
        assert {
            "xp",
            "risk_tolerance",
            "hp_current",
            "hp_max",
            "mana_current",
            "mana_max",
            "stamina_current",
            "stamina_max",
        }.issubset(simulated_player_columns)
        assert {"background", "profession_affinity_key"}.issubset(
            character_columns
        )
        assert "active_class_id" in character_columns
        class_offer_columns = {
            item["name"]
            for item in inspect(engine).get_columns("character_class_offers")
        }
        assert "sequence_number" in class_offer_columns
        class_definition_columns = {
            item["name"]
            for item in inspect(engine).get_columns("class_definitions")
        }
        assert {"identity", "theme", "generation_key"}.issubset(
            class_definition_columns
        )
        attribute_columns = {
            item["name"]
            for item in inspect(engine).get_columns("character_attributes")
        }
        assert {"key", "value", "development"}.issubset(attribute_columns)
        assert "name" not in attribute_columns
        attribute_constraints = {
            item["name"]
            for item in inspect(engine).get_unique_constraints(
                "character_attributes"
            )
        }
        assert "uq_character_attribute" in attribute_constraints
        with engine.connect() as connection:
            domain_count = connection.execute(
                text("SELECT COUNT(*) FROM domain_definitions")
            ).scalar_one()
            rare_domains = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT key FROM domain_definitions "
                        "WHERE key IN ('TIME', 'VOID', 'FATE')"
                    )
                )
            }
        assert domain_count >= 100
        assert rare_domains == {"TIME", "VOID", "FATE"}
        with engine.connect() as connection:
            attribute_keys = {
                row[0]
                for row in connection.execute(
                    text("SELECT key FROM attribute_definitions")
                )
            }
        assert attribute_keys == {
            "STRENGTH",
            "AGILITY",
            "VITALITY",
            "INTELLIGENCE",
            "WISDOM",
            "ENDURANCE",
            "LUCK",
        }
        assert "profession_affinity_key" in simulated_player_columns
        profession_constraints = {
            item["name"]
            for item in inspect(engine).get_unique_constraints(
                "character_professions"
            )
        }
        profession_xp_type = next(
            item["type"]
            for item in inspect(engine).get_columns("character_professions")
            if item["name"] == "xp"
        )
        assert "uq_character_profession" in profession_constraints
        assert profession_xp_type.python_type is float

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
