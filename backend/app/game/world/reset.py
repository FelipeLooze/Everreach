from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.campaign import Campaign, WorldTime
from app.db.models.character import Character, CharacterAttribute
from app.db.models.combat import (
    CombatAction,
    CombatCondition,
    CombatEncounter,
    CombatParticipant,
    CombatTurn,
    CombatTacticalAction,
)
from app.db.models.attribute import AttributeEvidenceRecord
from app.db.models.character_class import (
    CharacterClassOffer,
    ClassDefinition,
    ClassDefinitionDomain,
)
from app.db.models.event import WorldEvent
from app.db.models.domain import (
    CharacterDomainEvidence,
    CharacterDomainSynergy,
    DomainEvidenceRecord,
    DomainSynergyRecord,
)
from app.db.models.item import InventoryItem
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import CharacterLocationDiscovery, Location, LocationConnection, LocationFeature, CharacterConnectionDiscovery
from app.db.models.memory import Memory
from app.db.models.npc import NPC
from app.db.models.quest import CharacterQuest, CharacterQuestObjective, Quest, QuestObjective
from app.db.models.recovery import CharacterRecovery
from app.db.models.region import Region
from app.db.models.relationship import (
    CharacterNPCRelationship,
    CharacterSimulatedPlayerRelationship,
    SimulatedPlayerRelationship,
)
from app.db.models.resource import (
    CharacterResourceGrowth,
    ResourceGrowthEvidenceRecord,
)
from app.db.models.simulated_player import (
    SimulatedPlayer,
    SimulatedPlayerPopulation,
    SimulatedPlayerSkill,
)
from app.db.models.simulated_player_group import (
    SimulatedPlayerGroup,
    SimulatedPlayerGroupMember,
)
from app.db.models.simulated_player_routine import SimulatedPlayerRoutine
from app.db.models.simulated_player_arrival import (
    ScheduledSimulatedPlayerArrival,
    SimulatedPlayerArrivalLocation,
    SimulatedPlayerArrivalPolicy,
)
from app.db.models.skill import (
    CharacterSkill,
    CharacterTechnique,
    TechniqueUseRecord,
)
from app.db.models.profession import CharacterProfession
from app.db.models.progression_outcome import AppliedProgressionOutcome
from app.db.models.world_development import WorldDevelopment

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
    combat_ids = [
        row[0]
        for row in db.query(CombatEncounter.id).filter(
            CombatEncounter.campaign_id == campaign_id
        ).all()
    ]

    db.query(CombatCondition).filter(
        CombatCondition.encounter_id.in_(combat_ids)
    ).delete(synchronize_session=False)
    db.query(CombatTacticalAction).filter(
        CombatTacticalAction.encounter_id.in_(combat_ids)
    ).delete(synchronize_session=False)
    db.query(CombatAction).filter(
        CombatAction.encounter_id.in_(combat_ids)
    ).delete(synchronize_session=False)
    db.query(CombatTurn).filter(
        CombatTurn.encounter_id.in_(combat_ids)
    ).delete(synchronize_session=False)
    db.query(CombatParticipant).filter(
        CombatParticipant.encounter_id.in_(combat_ids)
    ).delete(synchronize_session=False)
    db.query(CombatEncounter).filter(
        CombatEncounter.id.in_(combat_ids)
    ).delete(synchronize_session=False)

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
    db.query(CharacterProfession).filter(
        CharacterProfession.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(AppliedProgressionOutcome).filter(
        AppliedProgressionOutcome.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(TechniqueUseRecord).filter(
        TechniqueUseRecord.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(CharacterClassOffer).filter(
        CharacterClassOffer.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(DomainEvidenceRecord).filter(
        DomainEvidenceRecord.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(DomainSynergyRecord).filter(
        DomainSynergyRecord.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(CharacterDomainSynergy).filter(
        CharacterDomainSynergy.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(CharacterDomainEvidence).filter(
        CharacterDomainEvidence.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(CharacterTechnique).filter(CharacterTechnique.character_id.in_(character_ids)).delete(
        synchronize_session=False
    )
    db.query(AttributeEvidenceRecord).filter(
        AttributeEvidenceRecord.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(ResourceGrowthEvidenceRecord).filter(
        ResourceGrowthEvidenceRecord.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(CharacterResourceGrowth).filter(
        CharacterResourceGrowth.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(CharacterRecovery).filter(
        CharacterRecovery.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
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
    db.query(CharacterSimulatedPlayerRelationship).filter(
        CharacterSimulatedPlayerRelationship.campaign_id == campaign_id
    ).delete(synchronize_session=False)
    db.query(SimulatedPlayerGroupMember).filter(
        SimulatedPlayerGroupMember.group_id.in_(
            db.query(SimulatedPlayerGroup.id).filter(
                SimulatedPlayerGroup.campaign_id == campaign_id
            )
        )
    ).delete(synchronize_session=False)
    db.query(SimulatedPlayerGroup).filter(
        SimulatedPlayerGroup.campaign_id == campaign_id
    ).delete(synchronize_session=False)
    db.query(SimulatedPlayerRelationship).filter(
        SimulatedPlayerRelationship.campaign_id == campaign_id
    ).delete(synchronize_session=False)
    simulated_player_ids = [
        row[0]
        for row in db.query(SimulatedPlayer.id).filter(
            SimulatedPlayer.campaign_id == campaign_id
        ).all()
    ]
    db.query(SimulatedPlayerSkill).filter(
        SimulatedPlayerSkill.simulated_player_id.in_(simulated_player_ids)
    ).delete(synchronize_session=False)
    db.query(SimulatedPlayerRoutine).filter(
        SimulatedPlayerRoutine.simulated_player_id.in_(simulated_player_ids)
    ).delete(synchronize_session=False)
    db.query(ScheduledSimulatedPlayerArrival).filter(
        ScheduledSimulatedPlayerArrival.location_id.in_(location_ids)
    ).delete(synchronize_session=False)
    db.query(SimulatedPlayerArrivalLocation).filter(
        SimulatedPlayerArrivalLocation.location_id.in_(location_ids)
    ).delete(synchronize_session=False)
    db.query(SimulatedPlayerArrivalPolicy).filter(
        SimulatedPlayerArrivalPolicy.campaign_id == campaign_id
    ).delete(synchronize_session=False)
    db.query(SimulatedPlayerPopulation).filter(
        SimulatedPlayerPopulation.location_id.in_(location_ids)
    ).delete(synchronize_session=False)
    db.query(WorldDevelopment).filter(WorldDevelopment.campaign_id == campaign_id).delete(synchronize_session=False)
    db.query(WorldEvent).filter(WorldEvent.campaign_id == campaign_id).delete(synchronize_session=False)
    db.query(NPC).filter(NPC.campaign_id == campaign_id).delete(synchronize_session=False)
    db.query(SimulatedPlayer).filter(SimulatedPlayer.campaign_id == campaign_id).delete(synchronize_session=False)
    db.query(CharacterLocationDiscovery).filter(
        or_(
            CharacterLocationDiscovery.character_id.in_(character_ids),
            CharacterLocationDiscovery.location_id.in_(location_ids),
        )
    ).delete(synchronize_session=False)
    db.query(CharacterConnectionDiscovery).filter(
        CharacterConnectionDiscovery.character_id.in_(character_ids)
    ).delete(synchronize_session=False)
    db.query(Character).filter(Character.id.in_(character_ids)).delete(synchronize_session=False)
    class_definition_ids = [
        row[0]
        for row in db.query(ClassDefinition.id).filter(
            ClassDefinition.campaign_id == campaign_id
        ).all()
    ]
    db.query(ClassDefinitionDomain).filter(
        ClassDefinitionDomain.class_definition_id.in_(class_definition_ids)
    ).delete(synchronize_session=False)
    db.query(ClassDefinition).filter(
        ClassDefinition.campaign_id == campaign_id
    ).delete(synchronize_session=False)

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
