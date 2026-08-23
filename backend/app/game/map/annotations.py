"""Phase 20J — Player Map Annotations.

"PLAYER NOTE != WORLD TRUTH" (spec) — see app.db.models.map_annotation
for the storage-level guarantee (a plain, Knowledge-free table). This
module is the one place allowed to write to it: create_annotation
requires the target Location to already be visible on the character's
own (unscoped) Map View, reusing get_map_view as the single source of
truth for "can this character legitimately see this location" instead
of re-deriving that gate here.
"""
from sqlalchemy.orm import Session

from app.db.models.map_annotation import MapAnnotation
from app.game.map.view import get_map_view


class AnnotationError(ValueError):
    pass


def create_annotation(
    db: Session,
    campaign_id: str,
    character_id: str,
    location_id: str,
    text: str,
) -> MapAnnotation:
    if not text or not text.strip():
        raise AnnotationError("A anotação não pode estar vazia.")

    view = get_map_view(db, campaign_id, character_id)
    visible_location_ids = {location.id for location in view.locations}
    if location_id not in visible_location_ids:
        raise AnnotationError("Você não pode anotar um local que não conhece.")

    annotation = MapAnnotation(
        campaign_id=campaign_id,
        character_id=character_id,
        location_id=location_id,
        text=text.strip(),
    )
    db.add(annotation)
    db.flush()
    return annotation


def list_annotations(db: Session, campaign_id: str, character_id: str) -> list[MapAnnotation]:
    return (
        db.query(MapAnnotation)
        .filter(
            MapAnnotation.campaign_id == campaign_id,
            MapAnnotation.character_id == character_id,
        )
        .order_by(MapAnnotation.created_at)
        .all()
    )


def delete_annotation(db: Session, character_id: str, annotation_id: str) -> bool:
    """Only the owning character may delete their own annotation.
    Returns False (never raises) for a missing or not-owned id — the
    caller can decide whether that is a 404 or a silent no-op."""
    annotation = db.get(MapAnnotation, annotation_id)
    if annotation is None or annotation.character_id != character_id:
        return False
    db.delete(annotation)
    db.flush()
    return True
