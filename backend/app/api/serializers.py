from sqlalchemy.orm import Session

from app.core.enums import KnowerType
from app.db.models.location import CharacterLocationDiscovery
from app.game.game_state import GameStateSnapshot
from app.game.knowledge.service import explicitly_knows_name
from app.schemas.character import CharacterResponse
from app.schemas.game_state import (
    ActiveQuestSummary,
    GameStateResponse,
    LocationSummary,
    NearbyNPC,
    NearbySimulatedPlayer,
    RegionSummary,
    SystemInventoryItemSummary,
    SystemInventorySummary,
    WorldTimeResponse,
)
from app.game.players.groups import active_group_for_player


def to_game_state_response(
    db: Session,
    state: GameStateSnapshot,
) -> GameStateResponse:
    location_name_known = (
        state.location is not None
        and explicitly_knows_name(
            db,
            state.campaign_id,
            KnowerType.PLAYER,
            state.character.id,
            state.location.name,
        )
    )

    region_name_known = (
        state.region is not None
        and explicitly_knows_name(
            db,
            state.campaign_id,
            KnowerType.PLAYER,
            state.character.id,
            state.region.name,
        )
    )

    location_discovery = (
        db.query(CharacterLocationDiscovery)
        .filter(
            CharacterLocationDiscovery.character_id == state.character.id,
            CharacterLocationDiscovery.location_id == state.location.id,
        )
        .first()
        if state.location is not None
        else None
    )

    return GameStateResponse(
        character=CharacterResponse.model_validate(state.character),
        region=(
            RegionSummary(
                id=state.region.id,
                name=state.region.name if region_name_known else None,
                description=None,
                discovery_status=state.region.discovery_status,
            )
            if state.region
            else None
        ),
        location=(
            LocationSummary(
                id=state.location.id,
                name=state.location.name if location_name_known else None,
                type=state.location.type,
                description=None,
                discovery_status=(
                    location_discovery.status
                    if location_discovery is not None
                    else "UNKNOWN"
                ),
            )
            if state.location
            else None
        ),
        world_time=(
            WorldTimeResponse.model_validate(state.world_time)
            if state.world_time
            else None
        ),
        nearby_npcs=[
            NearbyNPC(
                id=n.id,
                name=n.name,
                role=n.role,
                activity=n.activity,
            )
            for n in state.nearby_npcs
        ],
        nearby_simulated_players=[
            NearbySimulatedPlayer(
                id=p.id,
                name=p.name,
                level=p.level,
                xp=p.xp,
                archetype=p.archetype,
                risk_tolerance=p.risk_tolerance,
                goal=p.goal,
                group_id=(
                    group.id
                    if (group := active_group_for_player(db, p.id))
                    else None
                ),
            )
            for p in state.nearby_simulated_players
        ],
        active_quests=[
            ActiveQuestSummary(
                quest_id=q.id,
                name=q.name,
                status=cq.status,
            )
            for cq, q in state.active_quests
        ],
        inventory=SystemInventorySummary(
            items=[
                SystemInventoryItemSummary(
                    item_instance_id=item.item_instance_id,
                    name=item.name,
                    type=item.type,
                    quantity=item.quantity,
                    quality=item.quality,
                    condition=item.condition,
                    material_name=item.material_name,
                    equipped_slot=item.equipped_slot,
                    accessibility=item.accessibility,
                    contained_in_name=item.contained_in_name,
                )
                for item in state.inventory.items
            ],
            total_weight=state.inventory.total_weight,
            carrying_capacity=state.inventory.carrying_capacity,
            encumbrance=state.inventory.encumbrance,
        ),
        opening_narrative=state.opening_narrative,
        opening_narrator_unavailable=state.opening_narrator_unavailable,
    )
