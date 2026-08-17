from app.game.game_state import GameStateSnapshot
from app.schemas.character import CharacterResponse
from app.schemas.game_state import (
    ActiveQuestSummary,
    GameStateResponse,
    LocationSummary,
    NearbyNPC,
    NearbySimulatedPlayer,
    RegionSummary,
    WorldTimeResponse,
)


def to_game_state_response(state: GameStateSnapshot) -> GameStateResponse:
    return GameStateResponse(
        character=CharacterResponse.model_validate(state.character),
        region=RegionSummary.model_validate(state.region) if state.region else None,
        location=LocationSummary.model_validate(state.location) if state.location else None,
        world_time=WorldTimeResponse.model_validate(state.world_time) if state.world_time else None,
        nearby_npcs=[NearbyNPC(id=n.id, name=n.name, role=n.role) for n in state.nearby_npcs],
        nearby_simulated_players=[
            NearbySimulatedPlayer(id=p.id, name=p.name, level=p.level, archetype=p.archetype)
            for p in state.nearby_simulated_players
        ],
        active_quests=[
            ActiveQuestSummary(quest_id=q.id, name=q.name, status=cq.status) for cq, q in state.active_quests
        ],
        opening_narrative=state.opening_narrative,
        opening_narrator_unavailable=state.opening_narrator_unavailable,
    )
