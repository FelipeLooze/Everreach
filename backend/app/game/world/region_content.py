"""Shared region-content generation, extracted from
app.game.world.seed.seed_initial_region during Phase 16I so a second
(neighboring) Region can reuse the exact same settlement/road/POI/
organization/economy/threat pipeline instead of a parallel copy.

generate_region_settlements_and_infrastructure operates on whatever list
of already-persisted Subregion rows it's given — seed_initial_region
passes subregions[1:] (excluding its own hand-placed anchor village);
app.game.world.neighbor_region.materialize_neighbor_region (16I) passes
its entire subregion list, since a neighboring Region has no anchor
concept at all. Nothing about this function's logic changed from what
seed_initial_region used to do inline — only its location and its
subregion list moved from "always subregions[1:]" to "whatever the
caller passes".
"""

import random

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    ConnectionType,
    DiscoveryStatus,
    OrganizationOrigin,
    OrganizationType,
    OrganizationVisibility,
    PopulationDensity,
    SettlementType,
    SettlementWealthBand,
)
from app.db.models.location import Location, LocationConnection
from app.db.models.npc import NPC
from app.db.models.region import Region
from app.db.models.regional_threat import RegionalThreat
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.economy.local_economy import set_settlement_wealth
from app.game.economy.supply_demand import adjust_supply, get_or_create_supply_level
from app.game.inventory.service import get_or_create_item
from app.game.organizations.roles import create_role, join_organization
from app.game.organizations.service import create_organization
from app.game.world.generation import derive_seed
from app.game.world.generator import (
    EXPORT_SUPPLY_BONUS,
    choose_major_settlement_type,
    choose_minor_settlement_type,
    city_districts,
    danger_level_to_connection_danger,
    export_good_for_settlement,
    generate_leader_flavor,
    generate_npc_name,
    generate_pois,
    generate_settlement_name,
    generate_settlement_services,
    generate_subregion_geography,
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


def connect_locations(
    db: Session,
    a: Location,
    b: Location,
    direction_from_a: str,
    direction_from_b: str,
    distance: float,
    danger: int = 0,
    ctype=ConnectionType.PATH,
    modifier: float = 1.0,
) -> tuple[LocationConnection, LocationConnection]:
    """A plain bidirectional LocationConnection pair — the one place
    both seed_initial_region (for its hand-placed anchor flavor
    locations) and generate_region_settlements_and_infrastructure
    build connections, so the shape of a connection is defined once."""
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


def generate_region_settlements_and_infrastructure(
    db: Session,
    campaign_id: str,
    region: Region,
    region_seed: int,
    subregions: list[Subregion],
    used_location_names: set[str],
    used_npc_names: set[str],
    entry_location: Location | None = None,
) -> list[tuple[Subregion, Location, Settlement]]:
    """Generates geography, settlements, districts/services, roads, POIs,
    organizations and an economy/threat baseline for every subregion
    passed in. Returns major_settlement_rows (subregion, major
    settlement Location, Settlement) for the caller's own further use
    (e.g. arrival-policy wiring, which stays seed_initial_region's job).

    entry_location, if given, gets bridged (a real LocationConnection)
    into the first subregion's major settlement — seed_initial_region
    passes its anchor village's own road Location; a neighboring Region
    has nothing to bridge internally (that external link is 16Q's job,
    made after this function returns and the region's own entry
    settlement is known), so it passes None.
    """
    geography_features = []
    for subregion in subregions:
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

    major_settlement_rows: list[tuple[Subregion, Location, Settlement]] = []
    minor_settlement_locations: list[Location] = []

    for subregion in subregions:
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

    def connect(*args, **kwargs):
        return connect_locations(db, *args, **kwargs)

    if major_settlement_rows:
        roads_rng = random.Random(derive_seed(region_seed, "roads"))
        ordered_majors = sorted(major_settlement_rows, key=lambda row: row[0].order_index)

        if entry_location is not None:
            bridge_subregion, bridge_location, _bridge_settlement = ordered_majors[0]
            bridge_forward, bridge_back = roll_compass_direction_pair(roads_rng)
            connect(
                entry_location, bridge_location, bridge_forward, bridge_back,
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

    internal_rng = random.Random(derive_seed(region_seed, "settlement_internal"))
    locations_by_id = {
        location.id: location
        for _sub, location, _settlement in major_settlement_rows
    }
    locations_by_id.update({loc.id: loc for loc in district_locations})
    locations_by_id.update({loc.id: loc for loc in service_locations})
    for child in (*district_locations, *service_locations):
        parent = locations_by_id[child.parent_location_id]
        forward, back = roll_compass_direction_pair(internal_rng)
        connect(parent, child, forward, back, distance=0.2, danger=0)

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

    for subregion, major_location, _settlement in major_settlement_rows:
        org_rng = random.Random(derive_seed(subregion.generation_seed, "organization"))

        leader_name = generate_npc_name(org_rng, used_npc_names)
        organization_type = organization_type_for_settlement(_settlement.settlement_type)
        leader_title = leader_title_for_organization(organization_type)
        personality, backstory = generate_leader_flavor(org_rng)
        leader_npc = NPC(
            campaign_id=campaign_id, region_id=region.id, location_id=major_location.id,
            name=leader_name, role=leader_title,
            personality=personality, backstory=backstory,
        )
        db.add(leader_npc)
        db.flush()

        organization = create_organization(
            db, campaign_id,
            organization_name_for_settlement(major_location.name, organization_type),
            organization_type=OrganizationType(organization_type),
            origin=OrganizationOrigin.NATIVE,
            description=settlement_profile(_settlement.settlement_type),
            visibility=OrganizationVisibility.PUBLIC,
            headquarters_location_id=major_location.id,
            founder_type=CombatActorType.NPC,
            founder_id=leader_npc.id,
        )
        leader_role = create_role(db, organization, leader_title.capitalize(), rank_order=0)
        join_organization(db, organization, CombatActorType.NPC, leader_npc.id, role_id=leader_role.id)

    for subregion, major_location, settlement in major_settlement_rows:
        wealth_band = wealth_band_for_settlement(settlement.settlement_type)
        set_settlement_wealth(db, campaign_id, major_location.id, SettlementWealthBand(wealth_band))

        export_good_name = export_good_for_settlement(settlement.settlement_type)
        if export_good_name is not None:
            export_item = get_or_create_item(db, export_good_name)
            supply_level = get_or_create_supply_level(db, campaign_id, major_location.id, export_item.id)
            adjust_supply(
                db, supply_level, EXPORT_SUPPLY_BONUS,
                reason=f"{major_location.name} produz {export_good_name.lower()} localmente em abundância.",
            )

    for subregion in subregions:
        threat_rng = random.Random(derive_seed(subregion.generation_seed, "threat"))
        threat_type, threat_description = generate_threat(threat_rng)
        db.add(
            RegionalThreat(
                subregion_id=subregion.id,
                threat_type=threat_type,
                intensity=threat_intensity_for_danger_level(subregion.danger_level),
                description=threat_description,
            )
        )
    db.flush()

    return major_settlement_rows
