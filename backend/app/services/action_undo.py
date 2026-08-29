from __future__ import annotations

import base64
from datetime import UTC, date, datetime, time
from decimal import Decimal
import hashlib
import json
import zlib

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.base import Base
from app.db.models.action_checkpoint import ActionCheckpoint
from app.services.event_log import log_event


class ActionUndoError(Exception):
    pass


_EXCLUDED_TABLES = {ActionCheckpoint.__tablename__}


def _encode_value(value):
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"__type__": "time", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, bytes):
        return {"__type__": "bytes", "value": base64.b64encode(value).decode("ascii")}
    return value


def _decode_value(value):
    if not isinstance(value, dict) or "__type__" not in value:
        return value
    kind = value["__type__"]
    raw = value["value"]
    if kind == "datetime":
        return datetime.fromisoformat(raw)
    if kind == "date":
        return date.fromisoformat(raw)
    if kind == "time":
        return time.fromisoformat(raw)
    if kind == "decimal":
        return Decimal(raw)
    if kind == "bytes":
        return base64.b64decode(raw)
    raise ActionUndoError(f"Tipo de snapshot desconhecido: {kind}")


def _database_document(db: Session) -> dict[str, list[dict]]:
    document: dict[str, list[dict]] = {}
    connection = db.connection()
    for table in Base.metadata.sorted_tables:
        if table.name in _EXCLUDED_TABLES:
            continue
        rows = []
        for row in connection.execute(select(table)).mappings():
            rows.append({column.name: _encode_value(row[column.name]) for column in table.columns})
        rows.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        document[table.name] = rows
    return document


def _canonical_bytes(document: dict[str, list[dict]]) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pack(document: dict[str, list[dict]]) -> str:
    return base64.b64encode(zlib.compress(_canonical_bytes(document), level=6)).decode("ascii")


def _unpack(payload: str) -> dict[str, list[dict]]:
    try:
        raw = zlib.decompress(base64.b64decode(payload)).decode("utf-8")
        document = json.loads(raw)
    except (ValueError, zlib.error, json.JSONDecodeError) as exc:
        raise ActionUndoError("O checkpoint da ação está corrompido") from exc
    return {
        table_name: [
            {column_name: _decode_value(value) for column_name, value in row.items()}
            for row in rows
        ]
        for table_name, rows in document.items()
    }


def database_fingerprint(db: Session) -> str:
    return hashlib.sha256(_canonical_bytes(_database_document(db))).hexdigest()


def begin_action_checkpoint(
    db: Session,
    campaign_id: str,
    character_id: str,
    action_key: str,
    player_text: str,
) -> ActionCheckpoint:
    if db.get_bind().dialect.name != "sqlite":
        raise ActionUndoError("O desfazer seguro está disponível apenas no SQLite local")
    db.query(ActionCheckpoint).filter(
        ActionCheckpoint.status == "AVAILABLE"
    ).update(
        {ActionCheckpoint.status: "EXPIRED", ActionCheckpoint.snapshot_json: ""},
        synchronize_session=False,
    )
    db.flush()
    checkpoint = ActionCheckpoint(
        campaign_id=campaign_id,
        character_id=character_id,
        action_key=action_key,
        player_text=player_text,
        snapshot_json=_pack(_database_document(db)),
    )
    db.add(checkpoint)
    db.flush()
    return checkpoint


def finalize_action_checkpoint(
    db: Session,
    checkpoint_id: str,
    *,
    narrative: str,
    mechanical_summary: str,
) -> ActionCheckpoint:
    checkpoint = db.get(ActionCheckpoint, checkpoint_id)
    if checkpoint is None:
        raise ActionUndoError("O checkpoint da ação não foi encontrado")
    checkpoint.narrative = narrative
    checkpoint.mechanical_summary = mechanical_summary
    checkpoint.post_fingerprint = database_fingerprint(db)
    checkpoint.status = "AVAILABLE"
    db.commit()
    db.refresh(checkpoint)
    return checkpoint


def latest_available_checkpoint(
    db: Session, campaign_id: str, character_id: str
) -> ActionCheckpoint | None:
    return (
        db.query(ActionCheckpoint)
        .filter(
            ActionCheckpoint.campaign_id == campaign_id,
            ActionCheckpoint.character_id == character_id,
            ActionCheckpoint.status == "AVAILABLE",
        )
        .order_by(ActionCheckpoint.created_at.desc(), ActionCheckpoint.id.desc())
        .first()
    )


def checkpoint_is_current(db: Session, checkpoint: ActionCheckpoint) -> bool:
    return bool(
        checkpoint.post_fingerprint
        and checkpoint.post_fingerprint == database_fingerprint(db)
    )


def refresh_checkpoint_after_cosmetic_change(
    db: Session,
    checkpoint: ActionCheckpoint | None,
) -> None:
    if checkpoint is None:
        return
    checkpoint.post_fingerprint = database_fingerprint(db)
    db.flush()


def restore_last_action(
    db: Session,
    checkpoint: ActionCheckpoint,
    *,
    reason: str,
) -> None:
    if not checkpoint_is_current(db, checkpoint):
        raise ActionUndoError(
            "A ação não pode mais ser desfeita porque o estado do jogo mudou depois dela"
        )
    snapshot = _unpack(checkpoint.snapshot_json)
    checkpoint_id = checkpoint.id
    campaign_id = checkpoint.campaign_id
    character_id = checkpoint.character_id
    action_key = checkpoint.action_key
    player_text = checkpoint.player_text
    narrative = checkpoint.narrative
    mechanical_summary = checkpoint.mechanical_summary

    connection = db.connection()
    connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
    restorable_tables = [
        table for table in Base.metadata.sorted_tables if table.name not in _EXCLUDED_TABLES
    ]
    for table in reversed(restorable_tables):
        connection.execute(table.delete())
    for table in restorable_tables:
        rows = snapshot.get(table.name, [])
        if rows:
            connection.execute(table.insert(), rows)

    now = datetime.now(UTC).replace(tzinfo=None)
    connection.execute(
        update(ActionCheckpoint)
        .where(ActionCheckpoint.id == checkpoint_id)
        .values(
            status="UNDONE",
            snapshot_json="",
            undone_at=now,
            undo_reason=reason,
        )
    )
    db.expire_all()
    log_event(
        db,
        campaign_id,
        EventType.ACTION_UNDONE,
        actor_type="character",
        actor_id=character_id,
        payload={
            "action_key": action_key,
            "player_text": player_text,
            "previous_narrative": narrative,
            "mechanical_summary": mechanical_summary,
            "reason": reason,
        },
        importance=2,
    )
    db.commit()
