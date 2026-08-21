"""add jobs

Revision ID: ai14d1e2f3g4
Revises: ah14b1c2d3e4
Create Date: 2026-08-21

Phase 14D — Jobs & Work Opportunities: recurring/structured work,
distinct from a Quest (Phase 12, a situation/objective). One row per
employment stint (JobApplication), mirroring OrganizationMember (Phase
13F) — a rejection or an ended employment is preserved history, not
overwritten.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ai14d1e2f3g4"
down_revision: Union[str, None] = "ah14b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("employer_type", sa.String(), nullable=False),
        sa.Column("employer_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("location_id", sa.String(), nullable=True),
        sa.Column("wage_bronze", sa.Integer(), nullable=False),
        sa.Column("payment_frequency", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="OPEN"),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job_applications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("applicant_type", sa.String(), nullable=False),
        sa.Column("applicant_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("applied_world_minute", sa.Integer(), nullable=False),
        sa.Column("resolved_world_minute", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("job_applications")
    op.drop_table("jobs")
