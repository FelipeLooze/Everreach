from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus, EventType, KnowerType, connection_type_label_pt
from app.services.event_log import log_event
from app.db.models.character import Character
from app.db.models.location import (
    Location,
    LocationConnection,
    LocationFeature,
)
from app.game.discovery.service import (
    discover_connection,
    set_location_discovery,
)
from app.game.npcs.service import known_facts


def _explicit_name_known(facts, name: str | None) -> bool:
    """Same check context_builder._explicit_name_known makes for the
    player-facing "CONNECTED LOCATIONS KNOWN TO PLAYER" section —
    duplicated locally rather than imported across the game/ai layer
    boundary. observe_surroundings' own route text previously revealed
    a destination's canonical name unconditionally, with no equivalent
    gate at all (confirmed via live trace as a real regression: "PATH
    para Estalagem de Morven" was fed to the narrator as an AUTHORITATIVE
    MECHANICAL FACT before the player had ever learned the settlement's
    name), while the parallel context_builder section already redacted
    it to "Local desconhecido" — this closes that gap at the source."""
    if not name:
        return False
    normalized_name = name.casefold()
    return any(normalized_name in fact.statement.casefold() for fact in facts)


@dataclass
class PerceptionResult:
    location_name: str
    location_name_known: bool = True
    features: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    discovered_locations: list[str] = field(default_factory=list)
    discovered_connections: list[str] = field(default_factory=list)


def observe_surroundings(
    db: Session,
    character: Character,
) -> PerceptionResult:
    if character.location_id is None:
        raise ValueError("O personagem não possui localização atual.")

    location = db.get(Location, character.location_id)

    if location is None:
        raise ValueError("Localização atual não encontrada.")

    if location.genesis_site is not None:
        from app.game.world.genesis.territory import prepare_site
        from app.game.world.genesis.environment.service import query_environment
        from app.game.world.genesis.sphere_topology import SurfacePoint
        prepare_site(db, location)
        # Validate the actual current point; E1 potential is not established flora.
        query_environment(db, character.campaign_id, SurfacePoint(*location.genesis_site['point']))
        from app.db.models.campaign import Campaign
        from app.game.world.genesis.local_formations import nearby_signals
        campaign = db.get(Campaign, character.campaign_id)
        wgs1_signals = nearby_signals(db, campaign, location) if campaign is not None else []
        micro_facts = []
        if campaign is not None and campaign.world_profile in ("world_genesis_ap1_tp1_wgs2_v3", "world_genesis_ap1_tp1_wgs2_v4", "world_genesis_ap1_tp1_wgs2_v5", "world_genesis_ap1_tp1_wgs3_v1"):
            if campaign.world_profile in ("world_genesis_ap1_tp1_wgs2_v4", "world_genesis_ap1_tp1_wgs2_v5", "world_genesis_ap1_tp1_wgs3_v1"):
                from app.game.world.genesis.vegetation.service import context, microenvironment_context
                local = microenvironment_context(db, campaign.id, context(db, campaign.id), SurfacePoint(*location.genesis_site["point"]))
            else:
                from app.game.world.genesis.vegetation.microhabitat import resolve
                local = resolve(db, campaign.id, SurfacePoint(*location.genesis_site["point"]))
            if local is not None and "reduced_solar_exposure" in local["features"]:
                micro_facts.append("A área apresenta sombra local." if campaign.world_profile in ("world_genesis_ap1_tp1_wgs2_v4", "world_genesis_ap1_tp1_wgs2_v5", "world_genesis_ap1_tp1_wgs3_v1")
                    else "Sombra local: uma depressão protegida reduz a exposição solar.")
    else:
        wgs1_signals = []
        micro_facts = []

    features = (
        db.query(LocationFeature)
        .filter(
            LocationFeature.location_id == location.id,
            LocationFeature.visible.is_(True),
        )
        .order_by(LocationFeature.name)
        .all()
    )
    water_facts = None
    if location.genesis_site is not None and campaign is not None and campaign.world_profile == "world_genesis_ap1_tp1_wgs3_v1":
        from app.db.models.world_natural_formations import GenesisNaturalFormation
        from app.game.world.genesis.local_water import contract
        source = db.query(GenesisNaturalFormation).filter_by(location_id=location.id).one_or_none()
        if source is None and location.parent_location_id:
            source = db.query(GenesisNaturalFormation).filter_by(location_id=location.parent_location_id).one_or_none()
        if source is not None and source.archetype_id == "EV-LOC-0068":
            state = contract(db, source)
            water_facts = (["Há água visível numa fissura da formação. Fluxo e potabilidade não foram confirmados."]
                           if state["physical_water_present"] else
                           ["A fissura da nascente está visível, sem água neste estoque local."])

    connections = (
        db.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == location.id,
            LocationConnection.active.is_(True),
        )
        .all()
    )

    player_facts = known_facts(db, character.campaign_id, KnowerType.PLAYER, character.id)

    result = PerceptionResult(
        location_name=location.name,
        location_name_known=_explicit_name_known(player_facts, location.name),
        features=(water_facts if water_facts is not None else [
            f"{feature.name}: {feature.description}"
            for feature in features
        ]) + micro_facts,
        signals=wgs1_signals,
    )

    for connection in connections:
        destination = db.get(Location, connection.to_location_id)

        if destination is None:
            continue

        _connection_discovery, connection_changed = discover_connection(
            db,
            character.id,
            connection.id,
        )

        _location_discovery, location_changed = set_location_discovery(
            db,
            character.id,
            destination.id,
            DiscoveryStatus.DISCOVERED,
        )

        direction = connection.direction or "direção não registrada"
        destination_label = (
            destination.name
            if _explicit_name_known(player_facts, destination.name)
            else "um local desconhecido"
        )

        distance_label = (f"aproximadamente {round(connection.spatial_contract['metres'])} m"
                          if connection.spatial_contract else f"distância {connection.distance:g}")
        result.routes.append(
            f"{direction}: {connection_type_label_pt(connection.connection_type)} para "
            f"{destination_label} ({distance_label})"
        )

        if connection_changed:
            result.discovered_connections.append(connection.id)

            log_event(
                db,
                character.campaign_id,
                EventType.CONNECTION_DISCOVERED,
                actor_type="character",
                actor_id=character.id,
                payload={
                    "connection_id": connection.id,
                    "from_location_id": connection.from_location_id,
                    "to_location_id": connection.to_location_id,
                    "direction": connection.direction,
                    "connection_type": connection.connection_type,
                    "source": "observation",
                },
            )

        if location_changed:
            result.discovered_locations.append(destination.name)

            log_event(
                db,
                character.campaign_id,
                EventType.LOCATION_DISCOVERED,
                actor_type="character",
                actor_id=character.id,
                payload={
                    "location_id": destination.id,
                    "source": "observation",
                },
            )

    return result
