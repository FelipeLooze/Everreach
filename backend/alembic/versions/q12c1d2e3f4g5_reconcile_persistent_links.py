"""reconcile persistent organization and quest links

Revision ID: q12c1d2e3f4g5
Revises: p12b1c2d3e4f5
"""

from collections.abc import Sequence

from alembic import op

revision: str = "q12c1d2e3f4g5"
down_revision: str | None = "p12b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Earlier migrations added these nullable link columns but omitted the
    # ForeignKeyConstraint declared by the ORM models. Batch mode is required
    # because SQLite cannot add constraints in place.
    with op.batch_alter_table("notices") as batch_op:
        batch_op.create_foreign_key(
            "fk_notices_author_organization",
            "organizations",
            ["author_organization_id"],
            ["id"],
        )
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.create_foreign_key(
            "fk_organizations_founding_group",
            "groups",
            ["founding_group_id"],
            ["id"],
        )
    with op.batch_alter_table("quests") as batch_op:
        batch_op.create_foreign_key(
            "fk_quests_sponsoring_organization",
            "organizations",
            ["sponsoring_organization_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_quests_source_event",
            "world_events",
            ["source_event_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("quests") as batch_op:
        batch_op.drop_constraint("fk_quests_source_event", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_quests_sponsoring_organization", type_="foreignkey"
        )
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_constraint(
            "fk_organizations_founding_group", type_="foreignkey"
        )
    with op.batch_alter_table("notices") as batch_op:
        batch_op.drop_constraint(
            "fk_notices_author_organization", type_="foreignkey"
        )
