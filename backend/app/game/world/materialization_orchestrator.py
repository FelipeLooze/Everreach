"""Phase 16S — Transactional Persistence.

fulfill_region_materialization_request is the single call that turns a
PENDING RegionMaterializationRequest (16A) into a real, connected,
validated neighboring Region — generate → validate → persist, exactly
the staged flow the spec asks for (16I/16Q/16R composed in order).

No new transaction-management machinery exists here, because none was
needed: every step below already only writes through the caller's own
SQLAlchemy Session, and nothing in Everreach commits mid-request — the
existing pattern (see app.game.world.seed.seed_initial_region and
validate_region_package's own docstring) already makes the Session
itself the transaction boundary. This function deliberately does NOT
catch its own exceptions: a RegionValidationError or any other failure
propagates straight to the caller uncaught, so nothing it touched is
ever left half-committed — the caller's db.rollback() (or simply never
calling db.commit()) is "on failure: rollback" in full. Marking a
request REJECTED (app.game.world.region_materialization) is a separate,
deliberate decision a caller makes after giving up on retrying — never
an automatic side effect of a transient failure here.
"""

from sqlalchemy.orm import Session

from app.core.enums import RegionMaterializationRequestStatus
from app.db.models.region import Region
from app.db.models.region_materialization import RegionMaterializationRequest
from app.db.models.regional_boundary import RegionalBoundary
from app.game.world.cross_region_routes import connect_boundary_to_neighbor_region
from app.game.world.neighbor_region import materialize_neighbor_region
from app.game.world.region_materialization import mark_region_materialization_request_fulfilled
from app.game.world.validation import validate_neighbor_region_package


def fulfill_region_materialization_request(
    db: Session,
    request_id: str,
    boundary: RegionalBoundary,
    region_index: int,
) -> Region:
    request = db.get(RegionMaterializationRequest, request_id)
    if request is None:
        raise ValueError(f"Unknown region materialization request {request_id}")
    if request.status != RegionMaterializationRequestStatus.PENDING:
        raise ValueError(f"Request {request_id} is not PENDING (status={request.status}).")
    if request.source_region_id != boundary.source_region_id:
        raise ValueError(
            f"Request {request_id} is for source_region {request.source_region_id}, "
            f"but boundary {boundary.id} borders {boundary.source_region_id}."
        )

    neighbor = materialize_neighbor_region(db, request.campaign_id, boundary, region_index)
    connect_boundary_to_neighbor_region(db, boundary, neighbor)
    validate_neighbor_region_package(db, boundary, neighbor)

    mark_region_materialization_request_fulfilled(db, request.id, neighbor.id)

    return neighbor
