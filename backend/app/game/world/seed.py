import random

from sqlalchemy.orm import Session

from app.core.enums import (
    ConnectionType,
    DiscoveryStatus,
    EventType,
    KnowledgeCertainty,
    KnowerType,
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
    RiskTolerance,
)
from app.db.models.campaign import Campaign, WorldTime
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import Location, LocationConnection, LocationFeature
from app.db.models.npc import NPC
from app.db.models.region import Region
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.subregion import Subregion
from app.game.world.generation import CURRENT_REGION_GENERATION_VERSION, derive_seed
from app.game.world.generator import (
    generate_region_identity,
    generate_subregion_geography,
    generate_subregion_identity,
    generate_subregion_names,
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

    # Phase 15E — one major physical geography feature per non-anchor
    # subregion, matching its biome. The anchor subregion already has its
    # own bespoke geography above (forest/river/clearing); this only fills
    # in the rest of the massive region.
    geography_features = []
    for subregion in subregions[1:]:
        geo_rng = random.Random(derive_seed(subregion.generation_seed, "geography"))
        geo_name, geo_type, geo_description = generate_subregion_geography(geo_rng, subregion.biome)
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
    ) -> tuple[LocationConnection, LocationConnection]:
        outward = LocationConnection(
            from_location_id=a.id,
            to_location_id=b.id,
            direction=direction_from_a,
            connection_type=ctype,
            distance=distance,
            danger=danger,
        )
        returning = LocationConnection(
            from_location_id=b.id,
            to_location_id=a.id,
            direction=direction_from_b,
            connection_type=ctype,
            distance=distance,
            danger=danger,
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
