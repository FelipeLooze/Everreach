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

# Phase 21Q — the exact, closed set of future generated-asset kinds the
# spec names. This list exists ONLY to validate `asset_kind` on write
# (a typo'd kind should fail loudly, not silently create a new bucket
# no one will ever read) — it is never interpreted, never turned into
# a file path, and no code anywhere builds a ComfyUI prompt from it.
FUTURE_ASSET_KINDS = (
    "NPC_PORTRAIT",
    "NPC_FULL_BODY",
    "ITEM_ILLUSTRATION",
    "CREATURE_ILLUSTRATION",
    "LOCATION_SCENE",
    "SETTLEMENT_SCENE",
    "REGION_ART",
    "ORGANIZATION_EMBLEM",
    "MAP_ASSET",
)


class FutureAssetKindError(ValueError):
    pass


@dataclass(frozen=True)
class VisualSpec:
    subject_kind: str
    subject_id: str
    stable: dict = field(default_factory=dict)
    current: dict = field(default_factory=dict)
    assets: dict = field(default_factory=dict)


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
        assets=json.loads(row.asset_refs_json),
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
        asset_refs_json="{}",
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
        assets=json.loads(row.asset_refs_json),
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
        assets=json.loads(row.asset_refs_json),
    )


def set_visual_asset_reference(
    db: Session,
    subject_kind: str,
    subject_id: str,
    asset_kind: str,
    reference: str | None,
    *,
    campaign_id: str | None = None,
) -> VisualSpec:
    """Phase 21Q — records where a FUTURE generated asset lives, once
    one exists. `reference` is an opaque string this module never
    parses or builds (a future local asset id, most likely) — no
    ComfyUI path/URL shape is assumed or hardcoded here. Passing
    `reference=None` clears a previously-set reference (e.g. Canon
    changed enough that a stale asset must not be shown until
    regenerated), never leaves it dangling.
    """
    if asset_kind not in FUTURE_ASSET_KINDS:
        raise FutureAssetKindError(f"Unknown future asset kind: {asset_kind!r}")

    row = _get_or_create_row(db, subject_kind, subject_id, campaign_id)
    assets = json.loads(row.asset_refs_json)
    if reference is None:
        assets.pop(asset_kind, None)
    else:
        assets[asset_kind] = reference
    row.asset_refs_json = json.dumps(assets)
    db.flush()
    return VisualSpec(
        subject_kind=subject_kind, subject_id=subject_id,
        stable=json.loads(row.stable_json), current=json.loads(row.current_json),
        assets=assets,
    )


def resolve_visual_layers(*layers: dict) -> dict:
    """The one shared inheritance primitive every concrete entity
    resolver (21E NPC, 21G Location, 21H Settlement, 21I Subregion, ...)
    reuses: a plain, ordered, shallow merge — later layers override
    earlier ones key-by-key. "Do not create an uncontrolled style-
    resolution engine" (spec, mandatory): this is the whole engine, on
    purpose — Phase 21M audited every existing resolver and confirmed
    none of them reach for anything else.

    A key present in a later layer but mapped to None does NOT
    override an earlier layer's value for that key — "regional
    defaults must not overwrite explicit character state" only holds
    if the ABSENCE of a more specific fact never masquerades as an
    override. Callers represent "no opinion at this layer" as a
    missing key or an explicit None, never an empty string standing in
    for "unset."

    Phase 21M — canonical layer order per entity kind (broadest first,
    most specific/current last; every resolver below calls this
    function with its own layers already in this exact order — this
    comment is the one place documenting the whole set together, so a
    future subphase does not have to reverse-engineer it from five
    separate files):

      NPC (app.game.visual.npc.resolve_npc_appearance):
        region.stable -> npc.stable -> npc.current

      Location (app.game.visual.location.resolve_location_visual):
        region.stable -> subregion.stable -> location.stable -> location.current

      Settlement (app.game.visual.settlement.resolve_settlement_visual):
        resolve_location_visual(location) -> {settlement_scale, population_tier}
        -> settlement.stable -> settlement.current

      Subregion (app.game.visual.region.resolve_subregion_visual):
        region.stable -> subregion.stable -> subregion.current

      Regional threat / creature population
      (app.game.visual.creature.resolve_regional_threat_visual):
        threat_species.stable -> regional_threat.stable -> regional_threat.current

      Organization and Item do not have a resolve_*_visual function:
      an Item's spec (21D) is a flat read-derivation from Phase 10 Canon
      plus one optional signature_ornamentation trait — there is no
      broader-to-narrower chain to resolve. An Organization's heraldry
      (21J) is deliberately never blended with a broader default either
      — a "Global Style + Regional + Cultural + Organization" NPC-style
      chain has no Canon analogue for what an organization's emblem
      should default to; its stable/current traits are read directly.

      No entity kind currently has a real "Global Style" layer (the
      spec's own broadest tier): nothing in this codebase has
      established default appearance traits that should apply to every
      NPC/Location/Settlement before Region does. Adding an empty,
      unused layer to every resolver "for completeness" would be
      exactly the over-abstraction the spec warns against; a real
      global layer can be added to each resolver's own layer list the
      day some system actually needs to set one.
    """
    result: dict = {}
    for layer in layers:
        for key, value in layer.items():
            if value is not None:
                result[key] = value
    return result
