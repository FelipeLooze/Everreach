import random

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    ConnectionType,
    DiscoveryStatus,
    EventType,
    KnowledgeCertainty,
    KnowerType,
    OrganizationOrigin,
    OrganizationType,
    OrganizationVisibility,
    PopulationDensity,
    SettlementType,
    SettlementWealthBand,
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
    RiskTolerance,
)
from app.db.models.campaign import Campaign, WorldTime
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import Location, LocationConnection, LocationFeature
from app.db.models.npc import NPC
from app.db.models.region import Region
from app.db.models.regional_threat import RegionalThreat
from app.db.models.settlement import Settlement
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.subregion import Subregion
from app.game.economy.local_economy import set_settlement_wealth
from app.game.economy.supply_demand import adjust_supply, get_or_create_supply_level
from app.game.inventory.service import get_or_create_item
from app.game.organizations.roles import create_role, join_organization
from app.game.organizations.service import create_organization
from app.game.players.service import (
    set_simulated_player_arrival_location_enabled,
    set_simulated_player_arrival_policy,
)
from app.game.world.validation import validate_region_package
from app.game.world.generation import CURRENT_REGION_GENERATION_VERSION, derive_seed
from app.game.world.region_content import connect_locations, generate_region_settlements_and_infrastructure
from app.game.world.generator import (
    choose_major_settlement_type,
    choose_minor_settlement_type,
    city_districts,
    danger_level_to_connection_danger,
    EXPORT_SUPPLY_BONUS,
    export_good_for_settlement,
    generate_anchor_flavor_location,
    generate_blacksmith_flavor,
    generate_elder_flavor,
    generate_innkeeper_flavor,
    generate_leader_flavor,
    generate_npc_name,
    generate_region_identity,
    generate_region_name,
    generate_settlement_name,
    generate_settlement_services,
    generate_subregion_geography,
    generate_subregion_identity,
    generate_subregion_names,
    generate_pois,
    generate_threat,
    is_city_scale,
    leader_title_for_organization,
    minor_settlement_count,
    organization_name_for_settlement,
    organization_type_for_settlement,
    poi_connection_danger,
    roll_compass_direction_pair,
    roll_inter_subregion_distance,
    roll_local_distance,
    roll_poi_distance,
    settlement_population_tier,
    settlement_profile,
    threat_intensity_for_danger_level,
    travel_time_modifier_for_biome,
    wealth_band_for_settlement,
)
from app.services.event_log import log_event
from app.game.npcs.service import teach_fact

REGION_DESCRIPTION = (
    "Uma vasta região de escala quase continental, cujos limites mais distantes ninguém "
    "hoje vivo já mapeou por completo."
)

INITIAL_PLAYER_FACT_KEYS = ("arrival_square_visible",)


def create_campaign(db: Session, name: str, world_seed: int | None = None) -> Campaign:
    if world_seed is None:
        world_seed = random.SystemRandom().getrandbits(63)
    campaign = Campaign(name=name, world_seed=world_seed)
    db.add(campaign)
    db.flush()

    world_time = WorldTime(campaign_id=campaign.id, year=1, month=1, day=1, hour=8, minute=0)
    db.add(world_time)

    log_event(db, campaign.id, EventType.CAMPAIGN_CREATED, payload={"name": name})

    db.flush()
    return campaign


def seed_initial_region(db: Session, campaign_id: str) -> tuple[Region, Location]:
    """Create the single starting region for a fresh campaign. Only ever called once,
    when the player starts the world — later regions are created as the world progresses
    (spec section 6), not implemented yet in the MVP."""
    campaign = db.get(Campaign, campaign_id)
    if campaign.world_seed is None:
        # Self-heal saves created before Phase 15A introduced world_seed.
        campaign.world_seed = random.SystemRandom().getrandbits(63)

    region_seed = derive_seed(campaign.world_seed, "region:0")
    identity_rng = random.Random(derive_seed(region_seed, "identity"))
    climate_summary, cultural_summary, historical_summary = generate_region_identity(identity_rng)
    region_name = generate_region_name(random.Random(derive_seed(region_seed, "region_name")))

    region = Region(
        campaign_id=campaign_id,
        name=region_name,
        description=REGION_DESCRIPTION,
        discovery_status=DiscoveryStatus.DISCOVERED,
        generation_seed=region_seed,
        generation_version=CURRENT_REGION_GENERATION_VERSION,
        climate_summary=climate_summary,
        cultural_summary=cultural_summary,
        historical_summary=historical_summary,
    )
    db.add(region)
    db.flush()

    subregion_rng = random.Random(derive_seed(region_seed, "subregions"))
    subregion_names = generate_subregion_names(subregion_rng)
    subregions = []
    for index, name in enumerate(subregion_names):
        subregion_seed = derive_seed(region_seed, f"subregion:{index}")
        identity = generate_subregion_identity(
            random.Random(derive_seed(subregion_seed, "identity")),
            is_anchor=(index == 0),
        )
        subregions.append(
            Subregion(
                region_id=region.id,
                name=name,
                order_index=index,
                generation_seed=subregion_seed,
                **identity,
            )
        )
    db.add_all(subregions)
    db.flush()
    anchor_subregion = subregions[0]
    region.skeleton_complete = True

    # Phase 15 follow-up — the starting settlement is no longer a fixed
    # "Cardal": its name, and its 4 companion flavor locations' names/
    # descriptions, are generated per campaign like everything else in
    # Phase 15. They keep their original SHAPE (still exactly a village +
    # nearby forest/road/river/clearing, still the anchor subregion's own
    # bespoke geography rather than the generic 1-feature pool every
    # other subregion gets) — only the proper nouns became procedural.
    used_location_names: set[str] = set()
    anchor_flavor_rng = random.Random(derive_seed(anchor_subregion.generation_seed, "anchor_flavor"))

    village_name = generate_settlement_name(anchor_flavor_rng, used_location_names)
    forest_name, forest_description = generate_anchor_flavor_location(anchor_flavor_rng, "forest")
    used_location_names.add(forest_name)
    road_name, road_description = generate_anchor_flavor_location(anchor_flavor_rng, "road")
    used_location_names.add(road_name)
    river_name, river_description = generate_anchor_flavor_location(anchor_flavor_rng, "river")
    used_location_names.add(river_name)
    clearing_name, clearing_description = generate_anchor_flavor_location(anchor_flavor_rng, "clearing")
    used_location_names.add(clearing_name)

    village = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name=village_name,
        type="village",
        x=0,
        y=0,
        description="Uma pequena vila de mercado com casas de madeira e sapê ao redor de uma praça bem desgastada pelo uso.",
        discovery_status=DiscoveryStatus.VISITED,
    )
    forest_edge = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name=forest_name,
        type="forest",
        x=-2,
        y=1,
        description=forest_description,
        discovery_status=DiscoveryStatus.UNKNOWN,
    )
    road = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name=road_name,
        type="road",
        x=2,
        y=0,
        description=road_description,
        discovery_status=DiscoveryStatus.UNKNOWN,
    )
    creek = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name=river_name,
        type="river",
        x=0,
        y=-2,
        description=river_description,
        discovery_status=DiscoveryStatus.UNKNOWN,
    )
    clearing = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name=clearing_name,
        type="clearing",
        x=-4,
        y=2,
        description=clearing_description,
        discovery_status=DiscoveryStatus.UNKNOWN,
    )

    db.add_all([village, forest_edge, road, creek, clearing])
    db.flush()

    db.add_all(
        [
            LocationFeature(
                location_id=village.id,
                name="praça central",
                description=(
                    "Praça desgastada pelo uso, cercada por "
                    "casas de madeira e sapê."
                ),
            ),
            LocationFeature(
                location_id=forest_edge.id,
                name="orla da mata",
                description=(
                    "Árvores densas começam junto à borda do caminho "
                    "e a vegetação se torna mais fechada em direção ao oeste."
                ),
            ),
            LocationFeature(
                location_id=road.id,
                name="estrada de terra",
                description=(
                    "Faixa de terra batida segue em direção às terras "
                    "mais elevadas a leste."
                ),
            ),
            LocationFeature(
                location_id=creek.id,
                name="riacho",
                description=(
                    "Curso de água raso, de coloração escura, "
                    "atravessa o terreno."
                ),
            ),
            LocationFeature(
                location_id=clearing.id,
                name="clareira",
                description=(
                    "Uma abertura entre as árvores apresenta relva "
                    "pouco perturbada e poucos sinais imediatos de animais."
                ),
            ),
        ]
    )
    db.flush()

    forest_connection, _ = connect_locations(
        db, village, forest_edge, "noroeste", "sudeste", distance=1.0, danger=1
    )
    road_connection, _ = connect_locations(
        db, village, road, "leste", "oeste", distance=1.0, ctype=ConnectionType.ROAD
    )
    creek_connection, _ = connect_locations(
        db, village, creek, "sul", "norte", distance=0.8
    )
    connect_locations(db, forest_edge, clearing, "noroeste", "sudeste", distance=1.5, danger=2)
    db.flush()

    # Phase 15H (generalized 16I — see app.game.world.region_content) —
    # Settlements, districts/services, roads, POIs, organizations,
    # economy baseline and regional threats for every non-anchor
    # subregion. The anchor's own road Location (generated to already
    # lead "east toward the highlands" narratively) is the literal
    # bridge from the starting village into the chain — passed as
    # entry_location; app.game.world.neighbor_region.materialize_neighbor_region
    # (16I) calls the same function with entry_location=None since a
    # second Region's external link is 16Q's job, made from the outside.
    used_npc_names: set[str] = set()
    major_settlement_rows = generate_region_settlements_and_infrastructure(
        db, campaign_id, region, region_seed, subregions[1:],
        used_location_names, used_npc_names, entry_location=road,
    )

    # Phase 15 follow-up — the 3 starting NPCs keep their fixed ROLES
    # (many earlier-phase tests already look these up BY ROLE — "an
    # elder/leader", "a blacksmith", "an innkeeper" — as their standard
    # fixture), but their names and flavor text are generated per
    # campaign now, same as every other NPC Phase 15 creates.
    starting_npc_rng = random.Random(derive_seed(anchor_subregion.generation_seed, "starting_npcs"))

    elder_name = generate_npc_name(starting_npc_rng, used_npc_names)
    elder_personality, elder_backstory = generate_elder_flavor(starting_npc_rng, village.name)
    elder = NPC(
        campaign_id=campaign_id, region_id=region.id, location_id=village.id,
        name=elder_name, role="ancião da vila",
        personality=elder_personality,
        backstory=elder_backstory,
    )
    blacksmith_name = generate_npc_name(starting_npc_rng, used_npc_names)
    blacksmith_personality, blacksmith_backstory = generate_blacksmith_flavor(starting_npc_rng)
    blacksmith = NPC(
        campaign_id=campaign_id, region_id=region.id, location_id=village.id,
        name=blacksmith_name, role="ferreira",
        personality=blacksmith_personality,
        backstory=blacksmith_backstory,
    )
    innkeeper_name = generate_npc_name(starting_npc_rng, used_npc_names)
    innkeeper_personality, innkeeper_backstory = generate_innkeeper_flavor(starting_npc_rng, village.name)
    innkeeper = NPC(
        campaign_id=campaign_id, region_id=region.id, location_id=village.id,
        name=innkeeper_name, role="estalajadeiro",
        personality=innkeeper_personality,
        backstory=innkeeper_backstory,
    )
    db.add_all([elder, blacksmith, innkeeper])
    db.flush()

    # Phase 15 follow-up — settlement parity: the starting village used to
    # be the only VILLAGE-type settlement in the whole region without a
    # Settlement row (wealth band), an Organization, or the service
    # locations (inn/general store/blacksmith/notice board) every other
    # generated VILLAGE gets — a real content gap found by the user
    # ("só tem esses NPCs, ou são garantidos?"). Reuses the exact same
    # per-settlement machinery as every other subregion, with the
    # already-existing elder as the organization's founder/leader instead
    # of spawning a redundant 4th "village leader" NPC.
    village_settlement = Settlement(
        location_id=village.id,
        settlement_type=SettlementType.VILLAGE,
        profile=settlement_profile(SettlementType.VILLAGE),
        population_tier=settlement_population_tier(SettlementType.VILLAGE),
    )
    db.add(village_settlement)
    db.flush()

    village_org_type = organization_type_for_settlement(SettlementType.VILLAGE)
    village_org_leader_title = leader_title_for_organization(village_org_type)
    village_organization = create_organization(
        db, campaign_id,
        organization_name_for_settlement(village.name, village_org_type),
        organization_type=OrganizationType(village_org_type),
        origin=OrganizationOrigin.NATIVE,
        description=settlement_profile(SettlementType.VILLAGE),
        visibility=OrganizationVisibility.PUBLIC,
        headquarters_location_id=village.id,
        founder_type=CombatActorType.NPC,
        founder_id=elder.id,
    )
    village_org_role = create_role(db, village_organization, village_org_leader_title.capitalize(), rank_order=0)
    join_organization(db, village_organization, CombatActorType.NPC, elder.id, role_id=village_org_role.id)

    set_settlement_wealth(db, campaign_id, village.id, SettlementWealthBand(wealth_band_for_settlement(SettlementType.VILLAGE)))
    village_export_good_name = export_good_for_settlement(SettlementType.VILLAGE)
    if village_export_good_name is not None:
        village_export_item = get_or_create_item(db, village_export_good_name)
        village_supply_level = get_or_create_supply_level(db, campaign_id, village.id, village_export_item.id)
        adjust_supply(
            db, village_supply_level, EXPORT_SUPPLY_BONUS,
            reason=f"{village.name} produz {village_export_good_name.lower()} localmente em abundância.",
        )

    village_service_rng = random.Random(derive_seed(anchor_subregion.generation_seed, "village_services"))
    village_service_locations = []
    for service_name, service_type, service_description in generate_settlement_services(SettlementType.VILLAGE):
        village_service_locations.append(
            Location(
                region_id=region.id,
                subregion_id=anchor_subregion.id,
                parent_location_id=village.id,
                name=f"{service_name} de {village.name}",
                type=service_type,
                description=service_description,
                discovery_status=DiscoveryStatus.UNKNOWN,
                materialization_tier=1,
            )
        )
    db.add_all(village_service_locations)
    db.flush()
    for service_location in village_service_locations:
        forward, back = roll_compass_direction_pair(village_service_rng)
        connect_locations(db, village, service_location, forward, back, distance=0.2, danger=0)

    # Phase 15J (organizations), 15K (economy) and most of 15L (threats)
    # for every non-anchor subregion now happen inside
    # generate_region_settlements_and_infrastructure above. Only the
    # anchor subregion's own threat row (it was never part of
    # major_settlement_rows, which only ever covers subregions[1:])
    # still needs generating here.
    threat_rng = random.Random(derive_seed(anchor_subregion.generation_seed, "threat"))
    threat_type, threat_description = generate_threat(threat_rng)
    db.add(
        RegionalThreat(
            subregion_id=anchor_subregion.id,
            threat_type=threat_type,
            intensity=threat_intensity_for_danger_level(anchor_subregion.danger_level),
            description=threat_description,
        )
    )
    db.flush()

    # Phase 15 follow-up — fact_keys stay the exact same internal strings
    # as before (they're opaque lookup slugs, never displayed or matched
    # against — see app.game.knowledge.service.explicitly_knows_name,
    # which only ever inspects `statement` text, never `fact_key`). Only
    # the statements themselves need to become dynamic now that the
    # names they describe are generated per campaign.
    canonical_facts = [
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"location:{village.id}",
            fact_key="cardal_is_village",
            statement=f"{village.name} é uma vila da região {region.name}.",
        ),
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"location:{village.id}",
            fact_key="arrival_square_visible",
            statement="O local possui uma praça central cercada por casas de madeira e sapê.",
        ),
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"npc:{elder.id}",
            fact_key="osgar_born_in_cardal",
            statement=f"{elder.name} nasceu em {village.name} e vive ali há décadas.",
        ),
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"connection:{forest_connection.id}",
            fact_key="osgar_knows_cardal_northwest_path",
            statement=f"Uma trilha sai de {village.name} a noroeste em direção a {forest_edge.name}.",
        ),
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"connection:{road_connection.id}",
            fact_key="osgar_knows_cardal_east_road",
            statement=f"{road.name} sai de {village.name} para leste.",
        ),
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"connection:{creek_connection.id}",
            fact_key="osgar_knows_cardal_south_creek",
            statement=f"{creek.name} fica ao sul de {village.name} e é alcançado por uma trilha.",
        ),
    ]
    db.add_all(canonical_facts)
    db.flush()
    for fact in canonical_facts:
        db.add(
            KnowledgeKnower(
                fact_id=fact.id,
                knower_type=KnowerType.NPC.value,
                knower_id=elder.id,
                source="experiência local",
                certainty=KnowledgeCertainty.CONFIRMED.value,
            )
        )
    db.flush()

    simulated_players = [
        SimulatedPlayer(
            campaign_id=campaign_id,
            name="Corren Ashvale",
            level=0,
            location_id=village.id,
            archetype=SimulatedPlayerArchetype.EXPLORER,
            goal=f"Mapear os limites de {region.name}.",
            goal_type=SimulatedPlayerGoalType.EXPLORE_REGION,
            goal_subject=f"region:{region.id}",
            risk_tolerance=RiskTolerance.BALANCED.value,
        ),
        SimulatedPlayer(
            campaign_id=campaign_id,
            name="Dessa Marrow",
            level=0,
            location_id=village.id,
            archetype=SimulatedPlayerArchetype.TRAINER,
            goal="Aprender a sobreviver neste mundo desconhecido.",
            goal_type=SimulatedPlayerGoalType.TRAIN_SELF,
            goal_subject="level:1",
            risk_tolerance=RiskTolerance.CAUTIOUS.value,
        ),
        SimulatedPlayer(
            campaign_id=campaign_id,
            name="Bram Holt",
            level=0,
            location_id=village.id,
            archetype=SimulatedPlayerArchetype.SOCIAL,
            goal="Conseguir informações com os habitantes locais e outros recém-chegados.",
            goal_type=SimulatedPlayerGoalType.GATHER_KNOWLEDGE,
            goal_subject=f"location:{village.id}",
            risk_tolerance=RiskTolerance.BOLD.value,
        ),
    ]
    db.add_all(simulated_players)
    db.flush()

    # Phase 15 follow-up — Primeira Chegada keeps happening after world
    # start: transported people should keep arriving elsewhere over time
    # (Phase 7's ScheduledSimulatedPlayerArrival machinery), but neither
    # an arrival policy nor any eligible location was ever configured for
    # a real campaign before this — set_simulated_player_arrival_policy
    # and set_simulated_player_arrival_location_enabled were only ever
    # called from tests, so the whole mechanism sat unplugged. Every
    # major settlement (Tier 1, including the starting village) becomes
    # an eligible arrival point; selection is weighted by
    # Settlement.population_tier (see
    # app.game.players.service.select_simulated_player_arrival_location)
    # so most new arrivals land in bigger settlements — small villages
    # still get some, just proportionally fewer.
    set_simulated_player_arrival_policy(
        db, campaign_id,
        enabled=True,
        min_delay_minutes=60 * 24 * 3,
        max_delay_minutes=60 * 24 * 21,
        min_group_size=1,
        max_group_size=6,
    )
    set_simulated_player_arrival_location_enabled(db, campaign_id, village.id, enabled=True)
    for _subregion, major_location, _settlement in major_settlement_rows:
        set_simulated_player_arrival_location_enabled(db, campaign_id, major_location.id, enabled=True)

    # Phase 15Q — Region Validation & Persistence. An independent
    # consistency pass over what was just generated — not trusting the
    # generation-time bookkeeping (duplicate-name sets, connection
    # counts...) — before this is allowed to become committed Canon. The
    # caller (app.api.routes.campaigns.start_world) only commits after
    # this function returns; a RegionValidationError here means nothing
    # generated in this call is ever committed.
    validate_region_package(db, region)

    return region, village


def grant_initial_player_knowledge(db: Session, campaign_id: str, character_id: str) -> None:
    """Grant only facts immediately perceived at the starting location."""
    for fact_key in INITIAL_PLAYER_FACT_KEYS:
        teach_fact(
            db,
            campaign_id,
            fact_key,
            KnowerType.PLAYER,
            character_id,
            source="percepção direta",
            certainty=KnowledgeCertainty.CONFIRMED,
        )
