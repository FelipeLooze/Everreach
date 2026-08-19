"""add simulated player travel state

Revision ID: aab09fe9f20f
Revises: 016c02c3bb5f
Create Date: 2026-08-18 23:29:22.808736

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'aab09fe9f20f'
down_revision: Union[str, None] = '016c02c3bb5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.add_column(
            sa.Column(
                "travel_connection_id",
                sa.String(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "travel_destination_id",
                sa.String(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "travel_started_world_minute",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "travel_arrival_world_minute",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.create_foreign_key(
            "fk_simulated_players_travel_connection_id",
            "location_connections",
            ["travel_connection_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_simulated_players_travel_destination_id",
            "locations",
            ["travel_destination_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.drop_constraint(
            "fk_simulated_players_travel_destination_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_simulated_players_travel_connection_id",
            type_="foreignkey",
        )

        batch_op.drop_column("travel_arrival_world_minute")
        batch_op.drop_column("travel_started_world_minute")
        batch_op.drop_column("travel_destination_id")
        batch_op.drop_column("travel_connection_id")