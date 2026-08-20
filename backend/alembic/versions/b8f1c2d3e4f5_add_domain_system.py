"""add domain system

Revision ID: b8f1c2d3e4f5
Revises: a8e1b2c3d4e5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8f1c2d3e4f5"
down_revision: Union[str, None] = "a8e1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOMAIN_FAMILIES = {
    "WEAPON": "SWORD GREATSWORD DAGGER SPEAR POLEARM AXE HAMMER MACE STAFF BOW CROSSBOW THROWN_WEAPON SHIELD DUAL_WIELD UNARMED GRAPPLING IMPROVISED_WEAPON",
    "COMBAT_STYLE": "OFFENSE DEFENSE PRECISION POWER SPEED MOBILITY COUNTER DUELING SKIRMISH FORMATION BERSERK AMBUSH RANGED_COMBAT MOUNTED_COMBAT TACTICS COMMAND",
    "MAGIC_FOUNDATION": "MANA_SENSE MANA_CONTROL MANA_SHAPING ARCANE RITUAL RUNES ENCHANTMENT TRANSMUTATION ILLUSION DIVINATION SUMMONING WARDING RESTORATION NECROMANCY TELEKINESIS",
    "MANIFESTATION": "FIRE WATER WIND EARTH LIGHTNING ICE LIGHT SHADOW METAL PLANT POISON ACID SOUND SMOKE SAND CRYSTAL GRAVITY",
    "LIFE_NATURE_SPIRIT": "HEALING LIFE NATURE BEAST SPIRIT SOUL FAITH OATH PURIFICATION CURSE DEATH ANCESTOR FAMILIAR TAMING",
    "SUPPORT_CONTROL": "BARRIER BUFF DEBUFF CROWD_CONTROL DISRUPTION AURA PROTECTION CLEANSING SUPPRESSION DETECTION CONCEALMENT",
    "MOVEMENT": "ACROBATICS STEALTH AERIAL AQUATIC MOUNTED TELEPORTATION EVASION CHASE",
    "EXPLORATION": "TRACKING HUNTING SCOUTING NAVIGATION WILDERNESS TRAPS PERCEPTION INVESTIGATION SURVIVAL EXPLORATION",
    "MENTAL_SOCIAL_INTELLECTUAL": "SCHOLARSHIP RESEARCH ANALYSIS MEMORY LEADERSHIP INSPIRATION PERFORMANCE MUSIC INTIMIDATION DECEPTION DIPLOMACY STRATEGY",
    "RARE_EXOTIC": "SPACE TIME VOID DREAM CHAOS BLOOD BONE MIND FATE",
}


def upgrade() -> None:
    op.create_table(
        "domain_definitions",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("family", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    domain_table = sa.table(
        "domain_definitions",
        sa.column("key", sa.String()),
        sa.column("family", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        domain_table,
        [
            {"key": key, "family": family, "description": ""}
            for family, keys in DOMAIN_FAMILIES.items()
            for key in keys.split()
        ],
    )
    op.create_table(
        "character_domain_evidence",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("domain_key", sa.String(), nullable=False),
        sa.Column("depth", sa.Float(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["domain_key"], ["domain_definitions.key"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id", "domain_key", name="uq_character_domain_evidence"
        ),
    )
    op.create_table(
        "domain_evidence_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("domain_key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("evidence_key", sa.String(), nullable=False),
        sa.Column("context_key", sa.String(), nullable=False),
        sa.Column("base_amount", sa.Float(), nullable=False),
        sa.Column("awarded_amount", sa.Float(), nullable=False),
        sa.Column("repetition_count", sa.Integer(), nullable=False),
        sa.Column("world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["domain_key"], ["domain_definitions.key"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_domain_evidence_character_domain_time",
        "domain_evidence_records",
        ["character_id", "domain_key", "world_minute"],
    )
    op.create_table(
        "character_domain_synergies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("first_domain_key", sa.String(), nullable=False),
        sa.Column("second_domain_key", sa.String(), nullable=False),
        sa.Column("depth", sa.Float(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["first_domain_key"], ["domain_definitions.key"]),
        sa.ForeignKeyConstraint(["second_domain_key"], ["domain_definitions.key"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "first_domain_key",
            "second_domain_key",
            name="uq_character_domain_synergy",
        ),
    )
    op.create_table(
        "domain_synergy_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("first_domain_key", sa.String(), nullable=False),
        sa.Column("second_domain_key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("evidence_key", sa.String(), nullable=False),
        sa.Column("context_key", sa.String(), nullable=False),
        sa.Column("base_amount", sa.Float(), nullable=False),
        sa.Column("awarded_amount", sa.Float(), nullable=False),
        sa.Column("repetition_count", sa.Integer(), nullable=False),
        sa.Column("world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["first_domain_key"], ["domain_definitions.key"]),
        sa.ForeignKeyConstraint(["second_domain_key"], ["domain_definitions.key"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_domain_synergy_character_pair_time",
        "domain_synergy_records",
        ["character_id", "first_domain_key", "second_domain_key", "world_minute"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_domain_synergy_character_pair_time",
        table_name="domain_synergy_records",
    )
    op.drop_table("domain_synergy_records")
    op.drop_table("character_domain_synergies")
    op.drop_index(
        "ix_domain_evidence_character_domain_time",
        table_name="domain_evidence_records",
    )
    op.drop_table("domain_evidence_records")
    op.drop_table("character_domain_evidence")
    op.drop_table("domain_definitions")
