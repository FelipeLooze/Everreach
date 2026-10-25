"""Add daily village request director state and counted objectives.

Revision ID: g15g1b2c3d4e
Revises: f15f1a2b3c4d
"""

from alembic import op
import sqlalchemy as sa


revision = "g15g1b2c3d4e"
down_revision = "f15f1a2b3c4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("quests") as batch:
        batch.add_column(sa.Column("request_template_key", sa.String(), nullable=True))
        batch.add_column(sa.Column("request_generated_world_day", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("settlement_location_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("target_location_id", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_quests_settlement_location_id_locations",
            "locations", ["settlement_location_id"], ["id"],
        )
        batch.create_foreign_key(
            "fk_quests_target_location_id_locations",
            "locations", ["target_location_id"], ["id"],
        )
    with op.batch_alter_table("quest_objectives") as batch:
        batch.add_column(
            sa.Column("required_count", sa.Integer(), nullable=False, server_default="1")
        )
    with op.batch_alter_table("character_quest_objectives") as batch:
        batch.add_column(
            sa.Column("progress_count", sa.Integer(), nullable=False, server_default="0")
        )
    op.create_table(
        "daily_request_generations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("settlement_location_id", sa.String(), nullable=False),
        sa.Column("world_day", sa.Integer(), nullable=False),
        sa.Column("attempted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["settlement_location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "settlement_location_id", "world_day",
            name="uq_daily_request_generation_village_day",
        ),
    )


def downgrade() -> None:
    op.drop_table("daily_request_generations")
    with op.batch_alter_table("character_quest_objectives") as batch:
        batch.drop_column("progress_count")
    with op.batch_alter_table("quest_objectives") as batch:
        batch.drop_column("required_count")
    with op.batch_alter_table("quests") as batch:
        batch.drop_constraint("fk_quests_target_location_id_locations", type_="foreignkey")
        batch.drop_constraint("fk_quests_settlement_location_id_locations", type_="foreignkey")
        batch.drop_column("target_location_id")
        batch.drop_column("settlement_location_id")
        batch.drop_column("request_generated_world_day")
        batch.drop_column("request_template_key")
