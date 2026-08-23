from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.campaign import Campaign
from app.game.map.annotations import AnnotationError, create_annotation, delete_annotation
from app.game.map.planning import plan_known_route
from app.game.map.service import known_map
from app.game.map.view import get_map_view
from app.schemas.map import MapConnection, MapLocation, MapRegion, MapResponse
from app.schemas.map_view import (
    CreateMapAnnotationRequest,
    DeleteMapAnnotationResponse,
    MapViewAnnotationSchema,
    MapViewDataSchema,
    RoutePlanSchema,
    RoutePlanSegmentSchema,
)
from app.core.enums import DiscoveryStatus, KnowerType
from app.db.models.character import Character
from app.game.knowledge.service import explicitly_knows_name

router = APIRouter(prefix="/api/campaigns", tags=["map"])


def _load_character(db: Session, campaign_id: str, character_id: str) -> Character:
    if db.get(Campaign, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha")

    return character


@router.get("/{campaign_id}/map-view", response_model=MapViewDataSchema)
def get_player_map_view(
    campaign_id: str,
    character_id: str,
    scope: str | None = None,
    detail_level: str | None = None,
    min_x: float | None = None,
    min_y: float | None = None,
    max_x: float | None = None,
    max_y: float | None = None,
    db: Session = Depends(get_db),
):
    """Phase 20A/20B — the character-specific Map View projection, the
    contract the interactive frontend map (20B onward) consumes. Unlike
    /map (Phase 1, kept for backward compatibility), this always applies
    Phase 17B precision so vague/approximate Knowledge never leaks exact
    authoritative coordinates.

    Phase 20O — detail_level/min_x/min_y/max_x/max_y are optional LOD
    filters (see app.game.map.view's 20O docstring); all four bounds
    must be given together or the viewport filter is skipped entirely."""
    _load_character(db, campaign_id, character_id)
    viewport = None
    if None not in (min_x, min_y, max_x, max_y):
        viewport = (min_x, min_y, max_x, max_y)
    return get_map_view(
        db, campaign_id, character_id, scope=scope, detail_level=detail_level, viewport=viewport
    )


@router.get("/{campaign_id}/route-plan", response_model=RoutePlanSchema)
def get_route_plan(
    campaign_id: str,
    character_id: str,
    from_location_id: str,
    to_location_id: str,
    db: Session = Depends(get_db),
):
    """Phase 20M — Travel Planning Integration. Pathfinding restricted
    to the character's own known routes (see app.game.map.planning);
    `known=False` is the spec's own required "No known route" answer,
    not an error — this never falls back to the authoritative graph."""
    _load_character(db, campaign_id, character_id)
    plan = plan_known_route(db, campaign_id, character_id, from_location_id, to_location_id)
    if plan is None:
        return RoutePlanSchema(
            known=False,
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            segments=[],
            total_distance=0.0,
            estimated_minutes=0,
            max_danger=0,
        )
    return RoutePlanSchema(
        known=True,
        from_location_id=plan.from_location_id,
        to_location_id=plan.to_location_id,
        segments=[
            RoutePlanSegmentSchema(
                from_location_id=segment.from_location_id,
                to_location_id=segment.to_location_id,
                direction=segment.direction,
                connection_type=segment.connection_type,
                distance=segment.distance,
                danger=segment.danger,
            )
            for segment in plan.segments
        ],
        total_distance=plan.total_distance,
        estimated_minutes=plan.estimated_minutes,
        max_danger=plan.max_danger,
    )


@router.post("/{campaign_id}/map-annotations", response_model=MapViewAnnotationSchema, status_code=201)
def post_map_annotation(
    campaign_id: str,
    payload: CreateMapAnnotationRequest,
    db: Session = Depends(get_db),
):
    """Phase 20J — "PLAYER NOTE != WORLD TRUTH": create_annotation
    requires the target location to already be visible on the
    character's own Map View, so an annotation can never be pinned to
    something they have no legitimate reason to know about."""
    _load_character(db, campaign_id, payload.character_id)
    try:
        annotation = create_annotation(db, campaign_id, payload.character_id, payload.location_id, payload.text)
    except AnnotationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return MapViewAnnotationSchema(
        id=annotation.id,
        location_id=annotation.location_id,
        text=annotation.text,
        created_at=annotation.created_at.isoformat(),
    )


@router.delete("/{campaign_id}/map-annotations/{annotation_id}", response_model=DeleteMapAnnotationResponse)
def delete_map_annotation_route(
    campaign_id: str,
    annotation_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    _load_character(db, campaign_id, character_id)
    if not delete_annotation(db, character_id, annotation_id):
        raise HTTPException(status_code=404, detail="Anotação não encontrada")
    db.commit()
    return DeleteMapAnnotationResponse(deleted=True)


@router.get("/{campaign_id}/map", response_model=MapResponse)
def get_map(
    campaign_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    character = _load_character(db, campaign_id, character_id)

    data = known_map(
        db,
        campaign_id,
        character_id,
    )

    known_location_names = {
        loc.id: explicitly_knows_name(
            db,
            campaign_id,
            KnowerType.PLAYER,
            character.id,
            loc.name,
        )
        for loc in data["locations"]
    }

    known_region_names = {
        region.id: explicitly_knows_name(
            db,
            campaign_id,
            KnowerType.PLAYER,
            character.id,
            region.name,
        )
        for region in data["regions"]
    }

    locations = []

    for loc in data["locations"]:
        status = DiscoveryStatus(
            data["location_discovery"][loc.id]
        )

        coordinates_known = status in (
            DiscoveryStatus.DISCOVERED,
            DiscoveryStatus.VISITED,
            DiscoveryStatus.MAPPED,
        )

        locations.append(
            MapLocation(
                id=loc.id,
                region_id=loc.region_id,
                name=loc.name if known_location_names[loc.id] else None,
                type=loc.type,
                x=loc.x if coordinates_known else None,
                y=loc.y if coordinates_known else None,
                discovery_status=status.value,
            )
        )

    return MapResponse(
        regions=[
            MapRegion(
                id=region.id,
                name=(
                    region.name
                    if known_region_names[region.id]
                    else None
                ),
                description=None,
                discovery_status=region.discovery_status,
            )
            for region in data["regions"]
        ],
        locations=locations,
        connections=[
            MapConnection(
                from_location_id=connection.from_location_id,
                to_location_id=connection.to_location_id,
                direction=connection.direction,
                connection_type=connection.connection_type,
                distance=connection.distance,
                danger=connection.danger,
                travel_time_modifier=connection.travel_time_modifier,
            )
            for connection in data["connections"]
        ],
    )