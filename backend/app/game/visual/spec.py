"""Phase 21C — Structured Visual Specification Foundation.

VISUAL SPEC != IMAGE PROMPT (spec, mandatory). VisualSpec below is
canonical structured data about what an entity looks like — not a
sentence for an image generator. No prompt-building code exists
anywhere in this module or is planned for this phase; a future,
disposable prompt-builder step (Phase 21Q+/ComfyUI-adjacent, not part
of this phase) would read a VisualSpec, never the other way around.

STABLE vs CURRENT is the other mandatory split (see
app.db.models.visual_identity's own docstring for why it is a real
column split, not a text-field convention). set_stable_visual_traits
MERGES (an explicit Canon update to one trait — say, a new permanent
scar — must not silently erase every other already-established stable
trait); set_current_visual_state also merges, for the same practical
reason (changing "current clothing" must not blank out "visible
wounds") — CURRENT state is still free to be fully overwritten by a
caller that explicitly passes every key it wants representing "now".

WHICH keys belong in `stable` vs `current` for a given subject_kind is
each concrete entity subphase's own vocabulary (21D Item, 21E NPC, ...)
— nothing here validates or hard-codes field names, on purpose.
"""
import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models.visual_identity import VisualIdentity


@dataclass(frozen=True)
class VisualSpec:
    subject_kind: str
    subject_id: str
    stable: dict = field(default_factory=dict)
    current: dict = field(default_factory=dict)


def _get_row(
    db: Session, subject_kind: str, subject_id: str, campaign_id: str | None
) -> VisualIdentity | None:
    return (
        db.query(VisualIdentity)
        .filter(
            VisualIdentity.subject_kind == subject_kind,
            VisualIdentity.subject_id == subject_id,
            VisualIdentity.campaign_id == campaign_id,
        )
        .first()
    )


def get_visual_spec(
    db: Session,
    subject_kind: str,
    subject_id: str,
    *,
    campaign_id: str | None = None,
) -> VisualSpec:
    """Absence of a row means no visual data has been established yet —
    an empty VisualSpec, never an error (mirrors Knowledge's own
    "absence means unknown" convention)."""
    row = _get_row(db, subject_kind, subject_id, campaign_id)
    if row is None:
        return VisualSpec(subject_kind=subject_kind, subject_id=subject_id)
    return VisualSpec(
        subject_kind=subject_kind,
        subject_id=subject_id,
        stable=json.loads(row.stable_json),
        current=json.loads(row.current_json),
    )


def _get_or_create_row(
    db: Session, subject_kind: str, subject_id: str, campaign_id: str | None
) -> VisualIdentity:
    row = _get_row(db, subject_kind, subject_id, campaign_id)
    if row is not None:
        return row
    row = VisualIdentity(
        campaign_id=campaign_id,
        subject_kind=subject_kind,
        subject_id=subject_id,
        stable_json="{}",
        current_json="{}",
    )
    db.add(row)
    db.flush()
    return row


def set_stable_visual_traits(
    db: Session,
    subject_kind: str,
    subject_id: str,
    traits: dict,
    *,
    campaign_id: str | None = None,
) -> VisualSpec:
    row = _get_or_create_row(db, subject_kind, subject_id, campaign_id)
    stable = json.loads(row.stable_json)
    stable.update(traits)
    row.stable_json = json.dumps(stable)
    db.flush()
    return VisualSpec(
        subject_kind=subject_kind, subject_id=subject_id,
        stable=stable, current=json.loads(row.current_json),
    )


def set_current_visual_state(
    db: Session,
    subject_kind: str,
    subject_id: str,
    state: dict,
    *,
    campaign_id: str | None = None,
) -> VisualSpec:
    row = _get_or_create_row(db, subject_kind, subject_id, campaign_id)
    current = json.loads(row.current_json)
    current.update(state)
    row.current_json = json.dumps(current)
    db.flush()
    return VisualSpec(
        subject_kind=subject_kind, subject_id=subject_id,
        stable=json.loads(row.stable_json), current=current,
    )


def resolve_visual_layers(*layers: dict) -> dict:
    """The one shared inheritance primitive every concrete entity
    resolver (21E NPC, 21G Location, ...) reuses: a plain, ordered,
    shallow merge — later layers override earlier ones key-by-key.
    "Do not create an uncontrolled style-resolution engine" (spec,
    mandatory): this is the whole engine, on purpose.

    A key present in a later layer but mapped to None does NOT
    override an earlier layer's value for that key — "regional
    defaults must not overwrite explicit character state" only holds
    if the ABSENCE of a more specific fact never masquerades as an
    override. Callers represent "no opinion at this layer" as a
    missing key or an explicit None, never an empty string standing in
    for "unset."
    """
    result: dict = {}
    for layer in layers:
        for key, value in layer.items():
            if value is not None:
                result[key] = value
    return result
