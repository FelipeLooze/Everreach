"""Explicit preparation only; no streaming, ticks or commits owned by HR1."""
from app.db.models.world_hydrology_regional import GenesisHydrologyRefinement, GenesisHydrologyRegion
from ..formation_plan import cell_index, load_plan
from .regional import (RegionalHydrologyConfig, build_regional_hydrology, regional_sector_snapshot,
                       regional_signature, validate_region)
from .service import _header as h1_header, _source, get_hydrology_plan, payload_checksum


def _header(db, campaign_id):
    h1, source_config = h1_header(db, campaign_id)
    row = db.get(GenesisHydrologyRefinement, campaign_id)
    if row is None:
        raise ValueError("Initialize HR1 explicitly; legacy saves are not converted")
    config = RegionalHydrologyConfig.model_validate(row.config)
    # Signature helper uses only the immutable H1 signature, without loading its payload.
    expected = regional_signature(h1, config)
    if (type(row.refinement_version) is not int or row.refinement_version != 1 or row.signature != expected
            or row.hydrology_signature != h1.signature or row.hydrology_checksum != h1.payload_checksum):
        raise ValueError("HR1 version, configuration or H1 source changed")
    return row, config, source_config


def initialize_regional_hydrology(db, campaign_id, config=None):
    h1, _ = h1_header(db, campaign_id)
    existing = db.get(GenesisHydrologyRefinement, campaign_id)
    if existing is not None:
        row, pinned, _ = _header(db, campaign_id)
        if config is not None and config != pinned:
            raise ValueError("Cannot silently reconfigure HR1")
        return row
    config = config or RegionalHydrologyConfig()
    row = GenesisHydrologyRefinement(campaign_id=campaign_id, refinement_version=1,
        hydrology_signature=h1.signature, hydrology_checksum=h1.payload_checksum,
        signature=regional_signature(h1, config), config=config.model_dump())
    db.add(row)
    db.flush()
    return row


def materialize_hydrology_region(db, campaign_id, node):
    header, config, source_config = _header(db, campaign_id)
    from .config import HydrologyConfig
    h1_row, _ = h1_header(db, campaign_id)
    level = HydrologyConfig.model_validate(h1_row.config).level
    if type(node) is not int or not 0 <= node < 6*4**level:
        raise ValueError("Invalid pinned H1 region")
    existing = db.get(GenesisHydrologyRegion, (campaign_id, node))
    if existing is not None:
        data = existing.baseline
        if (existing.signature != header.signature or existing.baseline_checksum != payload_checksum(data)
                or data.get("signature") != header.signature or data.get("node") != node
                or data.get("source_signature") != _source(db, campaign_id)[0].plan["signature"]
                or data.get("hydrology_signature") != header.hydrology_signature or data.get("config") != header.config):
            raise ValueError("HR1 persisted region mismatch; refusing regeneration")
        validate_region(data)
        return existing
    world, _ = _source(db, campaign_id)
    source = load_plan(world.plan, world.world_seed, source_config)
    plan = get_hydrology_plan(db, campaign_id)
    baseline = build_regional_hydrology(source, plan, node, config)
    row = GenesisHydrologyRegion(campaign_id=campaign_id, node=node, signature=header.signature,
        baseline_checksum=payload_checksum(baseline), baseline=baseline, changes={})
    db.add(row)
    db.flush()
    return row


def query_hydrology_sector(db, campaign_id, key):
    """Prepares one canonical region if absent, then clips its saved baseline."""
    from .config import HydrologyConfig
    h1, source_config = h1_header(db, campaign_id)
    level = HydrologyConfig.model_validate(h1.config).level
    if key.level != source_config.sector_level or key.level < level:
        raise ValueError("HR1 sector query requires the pinned sector level at or below a macro cell")
    row = materialize_hydrology_region(db, campaign_id, cell_index(key.parent(level)))
    return {"baseline": regional_sector_snapshot(row.baseline, key), "changes": row.changes}
