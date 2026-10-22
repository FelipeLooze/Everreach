"""complete persistent technique discovery

Revision ID: o11a1b2c3d4e5
Revises: n10n1o2p3q4r5
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "o11a1b2c3d4e5"
down_revision: str | None = "n10n1o2p3q4r5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("character_technique_pattern_evidence") as batch_op:
        batch_op.add_column(sa.Column("recognized_technique_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "recognition_attempt_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("last_recognition_attempt_depth", sa.Float(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_technique_pattern_recognized_technique",
            "techniques",
            ["recognized_technique_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("character_technique_pattern_evidence") as batch_op:
        batch_op.drop_constraint(
            "fk_technique_pattern_recognized_technique", type_="foreignkey"
        )
        batch_op.drop_column("last_recognition_attempt_depth")
        batch_op.drop_column("recognition_attempt_count")
        batch_op.drop_column("recognized_technique_id")
