import random

from sqlalchemy.orm import Session

from app.core.enums import (
    ConnectionType,
    DiscoveryStatus,
    EventType,
    KnowledgeCertainty,
    KnowerType,
    PopulationDensity,
    SettlementType,
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
    RiskTolerance,
)
from app.db.models.campaign import Campaign, WorldTime
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import Location, LocationConnection, LocationFeature
from app.db.models.npc import NPC
from app.db.models.region import Region
from app.db.models.settlement import Settlement
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.subregion import Subregion
from app.game.world.generation import CURRENT_REGION_GENERATION_VERSION, derive_seed
from app.game.world.generator import (
    choose_major_settlement_type,
    choose_minor_settlement_type,
    city_districts,
    danger_level_to_connection_danger,
    generate_region_identity,
    generate_settlement_name,
    generate_settlement_services,
    generate_subregion_geography,
    generate_subregion_identity,
    generate_subregion_names,
    generate_pois,
    is_city_scale,
    minor_settlement_count,
    poi_connection_danger,
    roll_compass_direction_pair,
    roll_inter_subregion_distance,
    roll_local_distance,
    roll_poi_distance,
    settlement_population_tier,
    settlement_profile,
    travel_time_modifier_for_biome,
)
from app.services.event_log import log_event
from app.game.npcs.service import teach_fact

REGION_NAME = "Vale Verdejante"
REGION_DESCRIPTION = (
    "Uma região temperada de terras baixas, com campos ondulantes, matas antigas e uma "
    "única vila de mercado, cercada por colinas baixas cujo lado mais distante ninguém "
    "hoje vivo já mapeou."
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

    region = Region(
        campaign_id=campaign_id,
        name=REGION_NAME,
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

    village = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name="Cardal",
        type="village",
        x=0,
        y=0,
        description="Uma pequena vila de mercado com casas de madeira e sapê ao redor de uma praça bem desgastada pelo uso.",
        discovery_status=DiscoveryStatus.VISITED,
    )
    forest_edge = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name="Bosque da Beira do Vale",
        type="forest",
        x=-2,
        y=1,
        description="A orla mais próxima de uma mata densa que se espessa e escurece em direção ao oeste.",
        discovery_status=DiscoveryStatus.UNKNOWN,
    )
    road = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name="Estrada do Moinho",
        type="road",
        x=2,
        y=0,
        description="Uma estrada de terra batida que segue a leste da vila rumo às terras altas.",
        discovery_status=DiscoveryStatus.UNKNOWN,
    )
    creek = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name="Riacho Negro",
        type="river",
        x=0,
        y=-2,
        description="Um riacho raso de águas escuras ao sul da vila, bom para pescar.",
        discovery_status=DiscoveryStatus.UNKNOWN,
    )
    clearing = Location(
        region_id=region.id,
        subregion_id=anchor_subregion.id,
        name="Clareira do Vidro Antigo",
        type="clearing",
        x=-4,
        y=2,
        description="Uma clareira silenciosa no fundo da mata, cuja relva estranhamente não é perturbada por animais.",
        discovery_status=DiscoveryStatus.UNKNOWN,
    )

    db.add_all([village, forest_edge, road, creek, clearing])
    db.flush()

    used_location_names: set[str] = {
        village.name, forest_edge.name, road.name, creek.name, clearing.name,
    }

    # Phase 15E — one major physical geography feature per non-anchor
    # subregion, matching its biome. The anchor subregion already has its
    # own bespoke geography above (forest/river/clearing); this only fills
    # in the rest of the massive region.
    geography_features = []
    for subregion in subregions[1:]:
        geo_rng = random.Random(derive_seed(subregion.generation_seed, "geography"))
        geo_name, geo_type, geo_description = generate_subregion_geography(
            geo_rng, subregion.biome, used_location_names
        )
        geography_features.append(
            Location(
                region_id=region.id,
                subregion_id=subregion.id,
                name=geo_name,
                type=geo_type,
                description=geo_description,
                discovery_status=DiscoveryStatus.UNKNOWN,
            )
        )
    db.add_all(geography_features)
    db.flush()

    # Phase 15F — Settlement Network. Every non-anchor subregion gets one
    # major settlement (Tier 1, fully placed) plus a handful of minor
    # settlement stubs (Tier 2 — named, but not deep-materialized yet; see
    # Location.materialization_tier and Phase 15N/15P content-on-demand).
    # Exactly one eligible subregion's major settlement is upgraded to
    # MAJOR_CITY so the massive region has a single clear commercial peak,
    # matching the spec's own example scale ("several major cities").
    major_settlement_rows: list[tuple[Subregion, Location, Settlement]] = []
    minor_settlement_locations: list[Location] = []

    for subregion in subregions[1:]:
        settlement_rng = random.Random(derive_seed(subregion.generation_seed, "settlements"))

        major_type = choose_major_settlement_type(settlement_rng, subregion.biome)
        major_name = generate_settlement_name(settlement_rng, used_location_names)
        major_location = Location(
            region_id=region.id,
            subregion_id=subregion.id,
            name=major_name,
            type=major_type.lower(),
            description="",
            discovery_status=DiscoveryStatus.UNKNOWN,
            materialization_tier=1,
        )
        major_settlement = Settlement(
            settlement_type=major_type,
            profile=settlement_profile(major_type),
            population_tier=settlement_population_tier(major_type),
        )
        major_settlement_rows.append((subregion, major_location, major_settlement))

        for _ in range(minor_settlement_count(settlement_rng)):
            minor_type = choose_minor_settlement_type(settlement_rng)
            minor_name = generate_settlement_name(settlement_rng, used_location_names)
            minor_settlement_locations.append(
                Location(
                    region_id=region.id,
                    subregion_id=subregion.id,
                    name=minor_name,
                    type=minor_type.lower(),
                    description="",
                    discovery_status=DiscoveryStatus.UNKNOWN,
                    materialization_tier=2,
                )
            )

    db.add_all([location for _sub, location, _settlement in major_settlement_rows])
    db.add_all(minor_settlement_locations)
    db.flush()

    for subregion, location, settlement in major_settlement_rows:
        settlement.location_id = location.id
    db.add_all([settlement for _sub, _location, settlement in major_settlement_rows])
    db.flush()

    major_city_rng = random.Random(derive_seed(region_seed, "major_city"))
    dense_candidates = [
        (sub, loc, settlement)
        for sub, loc, settlement in major_settlement_rows
        if sub.population_density in (PopulationDensity.HIGH, PopulationDensity.DENSE)
    ]
    major_city_pool = dense_candidates or major_settlement_rows
    if major_city_pool:
        _chosen_sub, major_city_location, major_city_settlement = major_city_rng.choice(major_city_pool)
        major_city_location.type = SettlementType.MAJOR_CITY.lower()
        major_city_settlement.settlement_type = SettlementType.MAJOR_CITY
        major_city_settlement.profile = settlement_profile(SettlementType.MAJOR_CITY)
        major_city_settlement.population_tier = settlement_population_tier(SettlementType.MAJOR_CITY)
        db.flush()

    # Phase 15G — Settlement Internal Structure. Every major settlement
    # already knows which services it has (backend already knows "Cardal
    # has a blacksmith" — the protagonist doesn't have to walk around
    # until the LLM decides). MAJOR_CITY/CITY settlements get an extra
    # district layer; every other type attaches services directly.
    # Two passes: districts must be flushed (and have a real id) before
    # any service Location can reference one as its parent.
    central_district_by_settlement: dict[str, Location] = {}
    district_locations: list[Location] = []
    for subregion, location, settlement in major_settlement_rows:
        if not is_city_scale(settlement.settlement_type):
            continue
        for district_name, district_key in city_districts():
            district_location = Location(
                region_id=region.id,
                subregion_id=subregion.id,
                parent_location_id=location.id,
                name=f"{district_name} de {location.name}",
                type="district",
                description="",
                discovery_status=DiscoveryStatus.UNKNOWN,
                materialization_tier=(1 if district_key == "central" else 2),
            )
            district_locations.append(district_location)
            if district_key == "central":
                central_district_by_settlement[location.id] = district_location
    db.add_all(district_locations)
    db.flush()

    service_locations: list[Location] = []
    for subregion, location, settlement in major_settlement_rows:
        services = generate_settlement_services(settlement.settlement_type)
        services_parent = central_district_by_settlement.get(location.id, location)
        for service_name, service_type, service_description in services:
            service_locations.append(
                Location(
                    region_id=region.id,
                    subregion_id=subregion.id,
                    parent_location_id=services_parent.id,
                    name=f"{service_name} de {location.name}",
                    type=service_type,
                    description=service_description,
                    discovery_status=DiscoveryStatus.UNKNOWN,
                    materialization_tier=1,
                )
            )
    db.add_all(service_locations)
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

    def connect(
        a: Location,
        b: Location,
        direction_from_a: str,
        direction_from_b: str,
        distance: float,
        danger: int = 0,
        ctype=ConnectionType.PATH,
        modifier: float = 1.0,
    ) -> tuple[LocationConnection, LocationConnection]:
        outward = LocationConnection(
            from_location_id=a.id,
            to_location_id=b.id,
            direction=direction_from_a,
            connection_type=ctype,
            distance=distance,
            danger=danger,
            travel_time_modifier=modifier,
        )
        returning = LocationConnection(
            from_location_id=b.id,
            to_location_id=a.id,
            direction=direction_from_b,
            connection_type=ctype,
            distance=distance,
            danger=danger,
            travel_time_modifier=modifier,
        )
        db.add_all([outward, returning])
        db.flush()
        return outward, returning

    forest_connection, _ = connect(
        village, forest_edge, "noroeste", "sudeste", distance=1.0, danger=1
    )
    road_connection, _ = connect(
        village, road, "leste", "oeste", distance=1.0, ctype=ConnectionType.ROAD
    )
    creek_connection, _ = connect(
        village, creek, "sul", "norte", distance=0.8
    )
    connect(forest_edge, clearing, "noroeste", "sudeste", distance=1.5, danger=2)
    db.flush()

    # Phase 15H — Roads, Routes & Connections. Distances use the same
    # travel formula app.game.travel.service already owns (never a new
    # travel mechanic) — just scaled up so crossing subregions actually
    # takes days, not minutes. Non-anchor subregions form one chain (not a
    # fully connected mesh — the world needs empty stretches, spec), and
    # the existing "Estrada do Moinho" (already narrated as leading east
    # "rumo às terras altas") is the literal bridge from Cardal into it.
    if major_settlement_rows:
        roads_rng = random.Random(derive_seed(region_seed, "roads"))
        ordered_majors = sorted(major_settlement_rows, key=lambda row: row[0].order_index)

        bridge_subregion, bridge_location, _bridge_settlement = ordered_majors[0]
        bridge_forward, bridge_back = roll_compass_direction_pair(roads_rng)
        connect(
            road, bridge_location, bridge_forward, bridge_back,
            distance=roll_inter_subregion_distance(roads_rng),
            danger=danger_level_to_connection_danger(bridge_subregion.danger_level),
            ctype=ConnectionType.ROAD,
            modifier=travel_time_modifier_for_biome(bridge_subregion.biome),
        )

        for (prev_sub, prev_loc, _prev_settlement), (next_sub, next_loc, _next_settlement) in zip(
            ordered_majors, ordered_majors[1:]
        ):
            forward, back = roll_compass_direction_pair(roads_rng)
            connect(
                prev_loc, next_loc, forward, back,
                distance=roll_inter_subregion_distance(roads_rng),
                danger=danger_level_to_connection_danger(next_sub.danger_level),
                ctype=ConnectionType.ROAD,
                modifier=travel_time_modifier_for_biome(next_sub.biome),
            )

    # Local connections: each subregion's major settlement to its own
    # geography feature and to its own minor settlements — a subregion is
    # internally traversable even before any inter-subregion road exists.
    minor_by_subregion_id: dict[str, list[Location]] = {}
    for minor_location in minor_settlement_locations:
        minor_by_subregion_id.setdefault(minor_location.subregion_id, []).append(minor_location)
    geography_by_subregion_id = {loc.subregion_id: loc for loc in geography_features}

    for subregion, major_location, _settlement in major_settlement_rows:
        local_rng = random.Random(derive_seed(subregion.generation_seed, "local_roads"))

        geography_location = geography_by_subregion_id.get(subregion.id)
        if geography_location is not None:
            forward, back = roll_compass_direction_pair(local_rng)
            connect(
                major_location, geography_location, forward, back,
                distance=roll_local_distance(local_rng),
                danger=danger_level_to_connection_danger(subregion.danger_level),
            )

        for minor_location in minor_by_subregion_id.get(subregion.id, []):
            forward, back = roll_compass_direction_pair(local_rng)
            connect(
                major_location, minor_location, forward, back,
                distance=roll_local_distance(local_rng),
                danger=danger_level_to_connection_danger(subregion.danger_level),
            )

    # Phase 15I — Major Points of Interest. Persistent world truth, exists
    # whether or not the protagonist ever finds it — connected (remotely,
    # dangerously) to its subregion's major settlement so it's reachable
    # under the existing travel system, never floating disconnected.
    for subregion, major_location, _settlement in major_settlement_rows:
        poi_rng = random.Random(derive_seed(subregion.generation_seed, "pois"))
        for poi_name, poi_type, poi_description in generate_pois(poi_rng, used_location_names):
            poi_location = Location(
                region_id=region.id,
                subregion_id=subregion.id,
                name=poi_name,
                type=poi_type,
                description=poi_description,
                discovery_status=DiscoveryStatus.UNKNOWN,
                materialization_tier=1,
            )
            db.add(poi_location)
            db.flush()
            forward, back = roll_compass_direction_pair(poi_rng)
            connect(
                major_location, poi_location, forward, back,
                distance=roll_poi_distance(poi_rng),
                danger=poi_connection_danger(subregion.danger_level),
                ctype=ConnectionType.TRAIL,
            )

    elder = NPC(
        campaign_id=campaign_id, region_id=region.id, location_id=village.id,
        name="Osgar Vell", role="ancião da vila",
        personality="Paciente, atento, fala devagar e raramente repete o que diz.",
        backstory=(
            "Nasceu em Cardal, vive ali há décadas e lidera o conselho da vila há tanto tempo "
            "quanto a maioria dos moradores consegue lembrar."
        ),
    )
    blacksmith = NPC(
        campaign_id=campaign_id, region_id=region.id, location_id=village.id,
        name="Mira Draske", role="ferreira",
        personality="Direta, trabalhadora, orgulhosa do seu ofício.",
        backstory="Assumiu a forja do pai; desconfia de forasteiros que não pagam adiantado.",
    )
    innkeeper = NPC(
        campaign_id=campaign_id, region_id=region.id, location_id=village.id,
        name="Talven Brooks", role="estalajadeiro",
        personality="Falante, recolhe fofocas de todo viajante que passa por ali.",
        backstory="Administra a única estalagem da vila; conhece todos os boatos que circulam em Cardal.",
    )
    db.add_all([elder, blacksmith, innkeeper])
    db.flush()

    canonical_facts = [
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"location:{village.id}",
            fact_key="cardal_is_village",
            statement="Cardal é uma vila da região Vale Verdejante.",
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
            statement="Osgar Vell nasceu em Cardal e vive ali há décadas.",
        ),
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"connection:{forest_connection.id}",
            fact_key="osgar_knows_cardal_northwest_path",
            statement="Uma trilha sai de Cardal a noroeste em direção ao Bosque da Beira do Vale.",
        ),
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"connection:{road_connection.id}",
            fact_key="osgar_knows_cardal_east_road",
            statement="A Estrada do Moinho sai de Cardal para leste.",
        ),
        KnowledgeFact(
            campaign_id=campaign_id,
            subject=f"connection:{creek_connection.id}",
            fact_key="osgar_knows_cardal_south_creek",
            statement="O Riacho Negro fica ao sul de Cardal e é alcançado por uma trilha.",
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
            goal="Mapear os limites do Vale Verdejante.",
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
