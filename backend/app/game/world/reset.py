from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.campaign import Campaign, WorldTime
from app.db.models.character import Character, CharacterAttribute
from app.db.models.event import WorldEvent
from app.db.models.item import InventoryItem
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import CharacterLocationDiscovery, Location, LocationConnection, LocationFeature
from app.db.models.memory import Memory
from app.db.models.npc import NPC
from app.db.models.quest import CharacterQuest, CharacterQuestObjective, Quest, QuestObjective
from app.db.models.region import Region
from app.db.models.relationship import CharacterNPCRelationship
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.skill import CharacterSkill, CharacterTechnique


def delete_campaign(db: Session, campaign_id: str) -> bool:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return False

    region_ids = [row[0] for row in db.query(Region.id).filter(Region.campaign_id == campaign_id).all()]
    location_ids = [row[0] for row in db.query(Location.id).filter(Location.region_id.in_(region_ids)).all()]
    character_ids = [row[0] for row in db.query(Character.id).filter(Character.campaign_id == campaign_id).all()]
    quest_ids = [row[0] for row in db.query(Quest.id).filter(Quest.region_id.in_(region_ids)).all()]
    objective_ids = [row[0] for row in db.query(QuestObjective.id).filter(QuestObjective.quest_id.in_(quest_ids)).all()]
    fact_ids = [row[0] for row in db.query(KnowledgeFact.id).filter(KnowledgeFact.campaign_id == campaign_id).all()]

    db.query(CharacterQuestObjective).filter(
        or_(
            CharacterQuestObjective.character_id.in_(character_ids),
            CharacterQuestObjective.objective_id.in_(objective_ids),
        )
    ).delete(synchronize_session=False)
    db.query(CharacterQuest).filter(
        or_(CharacterQuest.character_id.in_(character_ids), CharacterQuest.quest_id.in_(quest_ids))
    ).delete(synchronize_session=False)
    db.query(CharacterSkill).filter(CharacterSkill.character_id.in_(character_ids)).delete(synchronize_session=False)
    db.query(CharacterTechnique).filter(CharacterTechnique.character_id.in_(character_ids)).delete(
        synchronize_session=False
    )
    db.query(InventoryItem).filter(InventoryItem.character_id.in_(character_ids)).delete(synchronize_session=False)
    db.query(CharacterAttribute).filter(CharacterAttribute.character_id.in_(character_ids)).delete(
        synchronize_session=False
    )

    db.query(QuestObjective).filter(QuestObjective.quest_id.in_(quest_ids)).delete(synchronize_session=False)
    db.query(Quest).filter(Quest.id.in_(quest_ids)).delete(synchronize_session=False)

    db.query(KnowledgeKnower).filter(KnowledgeKnower.fact_id.in_(fact_ids)).delete(synchronize_session=False)
    db.query(KnowledgeFact).filter(KnowledgeFact.id.in_(fact_ids)).delete(synchronize_session=False)

    db.query(Memory).filter(Memory.campaign_id == campaign_id).delete(synchronize_session=False)
    db.query(CharacterNPCRelationship).filter(
        CharacterNPCRelationship.campaign_id == campaign_id
    ).delete(synchronize_session=False)
    db.query(WorldEvent).filter(WorldEvent.campaign_id == campaign_id).delete(synchronize_session=False)
    db.query(NPC).filter(NPC.campaign_id == campaign_id).delete(synchronize_session=False)
    db.query(SimulatedPlayer).filter(SimulatedPlayer.campaign_id == campaign_id).delete(synchronize_session=False)
    db.query(CharacterLocationDiscovery).filter(
        or_(
            CharacterLocationDiscovery.character_id.in_(character_ids),
            CharacterLocationDiscovery.location_id.in_(location_ids),
        )
    ).delete(synchronize_session=False)
    db.query(Character).filter(Character.id.in_(character_ids)).delete(synchronize_session=False)

    db.query(LocationConnection).filter(
        or_(
            LocationConnection.from_location_id.in_(location_ids),
            LocationConnection.to_location_id.in_(location_ids),
        )
    ).delete(synchronize_session=False)
    db.query(LocationFeature).filter(LocationFeature.location_id.in_(location_ids)).delete(
        synchronize_session=False
    )
    db.query(Location).filter(Location.id.in_(location_ids)).delete(synchronize_session=False)
    db.query(Region).filter(Region.id.in_(region_ids)).delete(synchronize_session=False)

    db.query(WorldTime).filter(WorldTime.campaign_id == campaign_id).delete(synchronize_session=False)
    db.delete(campaign)
    db.flush()
    return True
