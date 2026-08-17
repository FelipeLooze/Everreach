"""canonical context and per-knower knowledge metadata

Revision ID: 2c01f4b8a912
Revises: 794ab7367771
Create Date: 2026-08-15
"""

from datetime import datetime, timezone
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "2c01f4b8a912"
down_revision: Union[str, None] = "794ab7367771"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _direction(dx: int, dy: int) -> str | None:
    horizontal = "leste" if dx > 0 else "oeste" if dx < 0 else ""
    vertical = "norte" if dy > 0 else "sul" if dy < 0 else ""
    if horizontal and vertical:
        return {
            ("norte", "leste"): "nordeste",
            ("norte", "oeste"): "noroeste",
            ("sul", "leste"): "sudeste",
            ("sul", "oeste"): "sudoeste",
        }[(vertical, horizontal)]
    return horizontal or vertical or None


def upgrade() -> None:
    op.add_column("location_connections", sa.Column("direction", sa.String(), nullable=True))
    op.add_column(
        "knowledge_facts",
        sa.Column("subject", sa.String(), nullable=False, server_default="world"),
    )
    op.add_column(
        "knowledge_knowers",
        sa.Column("source", sa.String(), nullable=False, server_default="system"),
    )
    op.add_column(
        "knowledge_knowers",
        sa.Column("certainty", sa.String(), nullable=False, server_default="CONFIRMED"),
    )
    op.add_column(
        "knowledge_knowers",
        sa.Column(
            "discovered_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_table(
        "location_features",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    bind = op.get_bind()
    locations = {
        row.id: row
        for row in bind.execute(sa.text("SELECT id, name, type, x, y FROM locations"))
    }
    connections = list(
        bind.execute(
            sa.text(
                "SELECT id, from_location_id, to_location_id FROM location_connections"
            )
        )
    )
    for connection in connections:
        origin = locations.get(connection.from_location_id)
        target = locations.get(connection.to_location_id)
        if origin is None or target is None:
            continue
        direction = _direction(target.x - origin.x, target.y - origin.y)
        bind.execute(
            sa.text("UPDATE location_connections SET direction=:direction WHERE id=:id"),
            {"direction": direction, "id": connection.id},
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cardal_rows = list(
        bind.execute(
            sa.text(
                "SELECT l.id, r.campaign_id FROM locations l "
                "JOIN regions r ON r.id=l.region_id WHERE l.name='Cardal'"
            )
        )
    )
    for cardal in cardal_rows:
        feature_exists = bind.execute(
            sa.text(
                "SELECT 1 FROM location_features "
                "WHERE location_id=:location_id AND name='praça central'"
            ),
            {"location_id": cardal.id},
        ).first()
        if not feature_exists:
            bind.execute(
                sa.text(
                    "INSERT INTO location_features "
                    "(id, location_id, name, description, visible) "
                    "VALUES (:id, :location_id, :name, :description, :visible)"
                ),
                {
                    "id": _id("feature"),
                    "location_id": cardal.id,
                    "name": "praça central",
                    "description": "Praça desgastada pelo uso, cercada por casas de madeira e sapê.",
                    "visible": True,
                },
            )

        osgar = bind.execute(
            sa.text(
                "SELECT id FROM npcs WHERE campaign_id=:campaign_id "
                "AND location_id=:location_id AND name='Osgar Vell'"
            ),
            {"campaign_id": cardal.campaign_id, "location_id": cardal.id},
        ).first()
        if osgar is not None:
            bind.execute(
                sa.text("UPDATE npcs SET backstory=:backstory WHERE id=:id"),
                {
                    "id": osgar.id,
                    "backstory": (
                        "Nasceu em Cardal, vive ali há décadas e lidera o conselho da vila há "
                        "tanto tempo quanto a maioria dos moradores consegue lembrar."
                    ),
                },
            )

        facts = [
            (
                "cardal_is_village",
                f"location:{cardal.id}",
                "Cardal é uma vila da região Vale Verdejante.",
            ),
            (
                "cardal_has_central_square",
                f"location:{cardal.id}",
                "Cardal possui uma praça central cercada por casas de madeira e sapê.",
            ),
        ]
        if osgar is not None:
            facts.append(
                (
                    "osgar_born_in_cardal",
                    f"npc:{osgar.id}",
                    "Osgar Vell nasceu em Cardal e vive ali há décadas.",
                )
            )
        route_keys = {
            "Bosque da Beira do Vale": "osgar_knows_cardal_northwest_path",
            "Estrada do Moinho": "osgar_knows_cardal_east_road",
            "Riacho Negro": "osgar_knows_cardal_south_creek",
        }
        for connection in connections:
            if connection.from_location_id != cardal.id:
                continue
            target = locations.get(connection.to_location_id)
            if target is None or target.name not in route_keys:
                continue
            direction = _direction(target.x - locations[cardal.id].x, target.y - locations[cardal.id].y)
            facts.append(
                (
                    route_keys[target.name],
                    f"connection:{connection.id}",
                    f"{target.name} fica a {direction} de Cardal e possui uma conexão registrada com a vila.",
                )
            )

        fact_ids: dict[str, str] = {}
        for fact_key, subject, statement in facts:
            existing = bind.execute(
                sa.text(
                    "SELECT id FROM knowledge_facts "
                    "WHERE campaign_id=:campaign_id AND fact_key=:fact_key"
                ),
                {"campaign_id": cardal.campaign_id, "fact_key": fact_key},
            ).first()
            fact_id = existing.id if existing else _id("fact")
            if existing is None:
                bind.execute(
                    sa.text(
                        "INSERT INTO knowledge_facts "
                        "(id, campaign_id, subject, fact_key, statement, is_secret) "
                        "VALUES (:id, :campaign_id, :subject, :fact_key, :statement, 0)"
                    ),
                    {
                        "id": fact_id,
                        "campaign_id": cardal.campaign_id,
                        "subject": subject,
                        "fact_key": fact_key,
                        "statement": statement,
                    },
                )
            fact_ids[fact_key] = fact_id

        if osgar is not None:
            for fact_id in fact_ids.values():
                bind.execute(
                    sa.text(
                        "INSERT INTO knowledge_knowers "
                        "(id, fact_id, knower_type, knower_id, source, certainty, discovered_at) "
                        "SELECT :id, :fact_id, 'NPC', :knower_id, :source, 'CONFIRMED', :discovered_at "
                        "WHERE NOT EXISTS (SELECT 1 FROM knowledge_knowers "
                        "WHERE fact_id=:fact_id AND knower_type='NPC' AND knower_id=:knower_id)"
                    ),
                    {
                        "id": _id("know"),
                        "fact_id": fact_id,
                        "knower_id": osgar.id,
                        "source": "experiência local",
                        "discovered_at": now,
                    },
                )

        characters = bind.execute(
            sa.text(
                "SELECT id FROM characters WHERE campaign_id=:campaign_id AND location_id=:location_id"
            ),
            {"campaign_id": cardal.campaign_id, "location_id": cardal.id},
        )
        for character in characters:
            for fact_key in ("cardal_is_village", "cardal_has_central_square"):
                bind.execute(
                    sa.text(
                        "INSERT INTO knowledge_knowers "
                        "(id, fact_id, knower_type, knower_id, source, certainty, discovered_at) "
                        "SELECT :id, :fact_id, 'PLAYER', :knower_id, :source, 'CONFIRMED', :discovered_at "
                        "WHERE NOT EXISTS (SELECT 1 FROM knowledge_knowers "
                        "WHERE fact_id=:fact_id AND knower_type='PLAYER' AND knower_id=:knower_id)"
                    ),
                    {
                        "id": _id("know"),
                        "fact_id": fact_ids[fact_key],
                        "knower_id": character.id,
                        "source": "percepção direta",
                        "discovered_at": now,
                    },
                )


def downgrade() -> None:
    op.drop_table("location_features")
    op.drop_column("knowledge_knowers", "discovered_at")
    op.drop_column("knowledge_knowers", "certainty")
    op.drop_column("knowledge_knowers", "source")
    op.drop_column("knowledge_facts", "subject")
    op.drop_column("location_connections", "direction")
