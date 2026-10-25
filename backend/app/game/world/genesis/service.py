"""Caller owns commit/rollback, as in existing region materialization."""
from sqlalchemy.orm import Session

from app.db.models.campaign import Campaign
from app.db.models.world_genesis import GenesisSector, GenesisWorld
from app.db.models.world_spatial import GenesisSphereSector
from .config import WorldConfig
from .coordinates import SectorKey, canonical_sector
from .geography import generate_sector, global_plan
from .sphere_config import SphereConfig, parse_config
from .sphere_topology import CellKey
from . import sphere_geography
from .formation_config import FormationConfig
from .formation_plan import build_plan, load_plan
from . import formation_geography


def initialize_world(db: Session, campaign_id: str, config: WorldConfig | SphereConfig | None = None) -> GenesisWorld:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.world_seed is None:
        raise ValueError("Genesis requires an existing campaign with a world seed")
    existing = db.get(GenesisWorld, campaign_id)
    if existing is not None:
        pinned = parse_config(existing.config)
        if campaign.world_seed != existing.world_seed or (config is not None and config != pinned):
            raise ValueError("Cannot change the seed or configuration of an existing Genesis world")
        return existing
    config = config or WorldConfig()
    if isinstance(config, FormationConfig):
        plan = build_plan(campaign.world_seed, config).to_dict()
    else:
        make_plan = sphere_geography.global_plan if isinstance(config, SphereConfig) else global_plan
        plan = make_plan(campaign.world_seed, config)
    world = GenesisWorld(campaign_id=campaign_id, world_seed=campaign.world_seed,
                         config=config.model_dump(mode="json"),
                         plan=plan)
    db.add(world)
    db.flush()
    return world


def materialize_sector(db: Session, campaign_id: str, key: SectorKey | CellKey) -> GenesisSector | GenesisSphereSector:
    world = db.get(GenesisWorld, campaign_id)
    if world is None:
        raise ValueError("Initialize Genesis explicitly before materializing sectors")
    config = parse_config(world.config)  # unsupported versions fail closed
    if isinstance(config, SphereConfig):
        if not isinstance(key, CellKey) or key.level != config.sector_level:
            raise ValueError("Spherical worlds require a CellKey at the pinned sector level")
        existing = db.get(GenesisSphereSector, (campaign_id, key.face, key.x, key.y))
        if existing is not None:
            return existing
        if isinstance(config, FormationConfig):
            baseline = formation_geography.generate_sector(load_plan(world.plan, world.world_seed, config), key)
        else:
            baseline = sphere_geography.generate_sector(world.world_seed, config, key)
        sector = GenesisSphereSector(campaign_id=campaign_id, face=key.face, x=key.x, y=key.y,
            baseline=baseline, changes={})
        db.add(sector)
        db.flush()
        return sector
    if not isinstance(key, SectorKey):
        raise ValueError("Legacy worlds require a cylindrical SectorKey")
    key = canonical_sector(config, key)
    existing = db.get(GenesisSector, (campaign_id, key.x, key.y))
    if existing is not None:
        return existing  # persisted baseline and changes always win
    sector = GenesisSector(campaign_id=campaign_id, x=key.x, y=key.y,
                           baseline=generate_sector(world.world_seed, config, key), changes={})
    db.add(sector)
    db.flush()
    return sector
