"""Phase 15Q — Region Validation & Persistence.

The generator does not get to unilaterally decide its own output is
Canon: validate_region_package re-checks the invariants the generation
pipeline (app.game.world.seed/generator) is supposed to already
guarantee, as an independent pass — not trusting the bookkeeping done
mid-generation. Called at the end of seed_initial_region, before the
caller's db.commit() — a validation failure raises, so nothing it
touched ever becomes committed Canon (the existing request-scoped
session is the transaction boundary; see this module's own docstring
note below on why generation isn't staged as a separate propose/validate/
persist pass).
"""

from sqlalchemy.orm import Session

from app.db.models.location import Location, LocationConnection
from app.db.models.organization import Organization
from app.db.models.region import Region
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.world.generator import MAX_SUBREGIONS, MIN_SUBREGIONS


class RegionValidationError(Exception):
    pass


def validate_region_package(db: Session, region: Region) -> None:
    """Cross-checks described by the Phase 15 spec ("CONSISTENCY PASSES"):
    duplicate names, dangling references, connectivity, scale. Raises
    RegionValidationError on the first violation found — this generator
    (version 1) is expected to always pass; a future generator version
    that doesn't would be caught here before its output could reach the
    player, not discovered later as a live bug."""
    if not region.skeleton_complete:
        raise RegionValidationError(
            f"Region {region.id} não completou a geração do esqueleto macro (skeleton_complete=False)."
        )

    subregions = db.query(Subregion).filter(Subregion.region_id == region.id).all()
    if not (MIN_SUBREGIONS <= len(subregions) <= MAX_SUBREGIONS):
        raise RegionValidationError(
            f"Region {region.id} tem {len(subregions)} subregiões, fora da faixa esperada "
            f"[{MIN_SUBREGIONS}, {MAX_SUBREGIONS}]."
        )

    locations = db.query(Location).filter(Location.region_id == region.id).all()
    names = [location.name for location in locations]
    if len(names) != len(set(names)):
        duplicates = {name for name in names if names.count(name) > 1}
        raise RegionValidationError(
            f"Region {region.id} tem nomes de localização duplicados: {sorted(duplicates)}."
        )

    location_ids = {location.id for location in locations}
    for location in locations:
        if location.subregion_id is not None and location.subregion_id not in {
            subregion.id for subregion in subregions
        }:
            raise RegionValidationError(
                f"Location {location.id} referencia subregion_id {location.subregion_id}, "
                "que não pertence a esta Region."
            )

    settlement_location_ids = {
        row[0]
        for row in db.query(Settlement.location_id)
        .filter(Settlement.location_id.in_(location_ids))
        .all()
    }
    connected_location_ids = {
        row[0]
        for row in db.query(LocationConnection.from_location_id)
        .filter(LocationConnection.from_location_id.in_(location_ids))
        .all()
    } | {
        row[0]
        for row in db.query(LocationConnection.to_location_id)
        .filter(LocationConnection.to_location_id.in_(location_ids))
        .all()
    }
    unreachable_settlements = settlement_location_ids - connected_location_ids
    if unreachable_settlements:
        raise RegionValidationError(
            f"Assentamentos sem nenhuma LocationConnection: {sorted(unreachable_settlements)}."
        )

    # Campaign-wide, not region-scoped: an organization headquartered in
    # a different (also valid) Region must not be flagged just because
    # its headquarters isn't among *this* Region's locations — the
    # invariant being checked is "no dangling reference", not "every
    # organization belongs to this Region" (only ever surfaced once a
    # second Region could exist at all, Phase 16I).
    all_campaign_location_ids = {
        row[0]
        for row in db.query(Location.id)
        .join(Region, Location.region_id == Region.id)
        .filter(Region.campaign_id == region.campaign_id)
        .all()
    }
    organizations = db.query(Organization).filter(Organization.campaign_id == region.campaign_id).all()
    for organization in organizations:
        if (
            organization.headquarters_location_id is not None
            and organization.headquarters_location_id not in all_campaign_location_ids
        ):
            raise RegionValidationError(
                f"Organization {organization.id} referencia headquarters_location_id "
                f"{organization.headquarters_location_id}, que não existe em nenhuma Region da campanha."
            )
