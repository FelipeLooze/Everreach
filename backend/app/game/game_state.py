from dataclasses import dataclass
import json

from sqlalchemy.orm import Session

from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.quest import CharacterQuest, Quest
from app.db.models.region import Region
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.campaign import WorldTime
from app.db.models.event import WorldEvent
from app.core.enums import EventType
from app.game.npcs.service import npcs_at_location
from app.game.players.service import simulated_players_at_location
from app.game.quests.service import list_character_quests


@dataclass
class GameStateSnapshot:
    """A read-only aggregation of the currently relevant world state. This is a view,
    not an owner of state — all mutation happens through the domain services."""

    campaign_id: str
    character: Character
    region: Region | None
    location: Location | None
    world_time: WorldTime
    nearby_npcs: list[NPC]
    nearby_simulated_players: list[SimulatedPlayer]
    active_quests: list[tuple[CharacterQuest, Quest]]
    opening_narrative: str | None
    opening_narrator_unavailable: bool


def build_game_state(db: Session, campaign_id: str, character_id: str) -> GameStateSnapshot:
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise ValueError(f"Personagem desconhecido nesta campanha: {character_id}")

    region = db.get(Region, character.region_id) if character.region_id else None
    location = db.get(Location, character.location_id) if character.location_id else None
    world_time = db.query(WorldTime).filter(WorldTime.campaign_id == campaign_id).first()

    nearby_npcs = npcs_at_location(db, character.location_id) if character.location_id else []
    nearby_players = simulated_players_at_location(db, character.location_id) if character.location_id else []

    quest_links = list_character_quests(db, character_id)
    active_quests = [
        (cq, db.get(Quest, cq.quest_id)) for cq in quest_links if db.get(Quest, cq.quest_id) is not None
    ]

    opening_event = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.event_type == EventType.WORLD_STARTED,
            WorldEvent.actor_id == character_id,
        )
        .order_by(WorldEvent.created_at.desc())
        .first()
    )
    opening_payload = json.loads(opening_event.payload_json) if opening_event else {}

    return GameStateSnapshot(
        campaign_id=campaign_id,
        character=character,
        region=region,
        location=location,
        world_time=world_time,
        nearby_npcs=nearby_npcs,
        nearby_simulated_players=nearby_players,
        active_quests=active_quests,
        opening_narrative=opening_payload.get("narrative"),
        opening_narrator_unavailable=bool(opening_payload.get("narrator_unavailable", False)),
    )
