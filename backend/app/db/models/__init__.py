from app.db.models.campaign import Campaign, WorldTime
from app.db.models.attribute import AttributeDefinition, AttributeEvidenceRecord
from app.db.models.character import Character, CharacterAttribute
from app.db.models.container import ItemContainerProfile
from app.db.models.combat import (
    CombatAction,
    CombatAutonomousDecision,
    CombatCondition,
    CombatCriticalCheck,
    CombatEncounter,
    CombatIncapacitation,
    CombatParticipant,
    CombatTurn,
    CombatTacticalAction,
)
from app.db.models.character_class import (
    CharacterClassOffer,
    ClassDefinition,
    ClassDefinitionDomain,
)
from app.db.models.event import WorldEvent
from app.db.models.group import Group, GroupInvite, GroupMember
from app.db.models.domain import (
    CharacterDomainEvidence,
    CharacterDomainSynergy,
    DomainDefinition,
    DomainEvidenceRecord,
    DomainSynergyRecord,
)
from app.db.models.defense import ActorCombatDefense, ItemArmorProfile, ItemCombatProfile
from app.db.models.equipment import ItemEquipmentProfile
from app.db.models.item import Item, ItemDefinition, ItemInstance, ItemWearRecord
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import (
    CharacterConnectionDiscovery,
    CharacterLocationDiscovery,
    Location,
    LocationConnection,
    LocationFeature,
)
from app.db.models.memory import Memory
from app.db.models.material import MaterialDefinition
from app.db.models.notice import Notice
from app.db.models.npc import NPC
from app.db.models.profession import CharacterProfession, Profession
from app.db.models.progression_outcome import AppliedProgressionOutcome
from app.db.models.quest import (
    CharacterQuest,
    CharacterQuestObjective,
    Quest,
    QuestObjective,
)
from app.db.models.recovery import CharacterRecovery
from app.db.models.simulated_player_arrival import (
    SimulatedPlayerArrivalLocation,
    ScheduledSimulatedPlayerArrival,
    SimulatedPlayerArrivalPolicy,
)
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
from app.db.models.simulated_player_routine import (
    SimulatedPlayerRoutine,
)
from app.db.models.technique_evidence import (
    CharacterTechniquePatternEvidence,
    TechniqueExperimentRecord,
    TechniquePatternEvidenceRecord,
)
from app.db.models.skill import (
    CharacterSkill,
    CharacterTechnique,
    CombatTechniqueProfile,
    Skill,
    Technique,
    TechniqueDomain,
    TechniqueUseRecord,
)
from app.db.models.world_development import WorldDevelopment
from app.db.models.tool import ItemToolProfile
from app.db.models.weapon import ItemWeaponProfile

__all__ = [
    "Campaign",
    "AttributeDefinition",
    "AttributeEvidenceRecord",
    "WorldTime",
    "Character",
    "CharacterAttribute",
    "CombatEncounter",
    "CombatAction",
    "CombatAutonomousDecision",
    "CombatCondition",
    "CombatCriticalCheck",
    "CombatIncapacitation",
    "CombatTacticalAction",
    "CombatParticipant",
    "CombatTurn",
    "ClassDefinition",
    "ClassDefinitionDomain",
    "CharacterClassOffer",
    "WorldEvent",
    "Group",
    "GroupMember",
    "GroupInvite",
    "DomainDefinition",
    "CharacterDomainEvidence",
    "DomainEvidenceRecord",
    "CharacterDomainSynergy",
    "DomainSynergyRecord",
    "ActorCombatDefense",
    "ItemCombatProfile",
    "ItemArmorProfile",
    "ItemEquipmentProfile",
    "ItemContainerProfile",
    "Item",
    "ItemDefinition",
    "ItemInstance",
    "ItemWearRecord",
    "KnowledgeFact",
    "KnowledgeKnower",
    "CharacterConnectionDiscovery",
    "CharacterLocationDiscovery",
    "Location",
    "LocationConnection",
    "LocationFeature",
    "Memory",
    "MaterialDefinition",
    "Notice",
    "NPC",
    "Profession",
    "CharacterProfession",
    "AppliedProgressionOutcome",
    "CharacterQuest",
    "CharacterQuestObjective",
    "Quest",
    "QuestObjective",
    "CharacterRecovery",
    "Region",
    "CharacterNPCRelationship",
    "CharacterSimulatedPlayerRelationship",
    "SimulatedPlayerRelationship",
    "CharacterResourceGrowth",
    "ResourceGrowthEvidenceRecord",
    "ScheduledSimulatedPlayerArrival",
    "SimulatedPlayer",
    "SimulatedPlayerPopulation",
    "SimulatedPlayerSkill",
    "SimulatedPlayerGroup",
    "SimulatedPlayerGroupMember",
    "SimulatedPlayerRoutine",
    "SimulatedPlayerArrivalPolicy",
    "SimulatedPlayerArrivalLocation",
    "CharacterTechniquePatternEvidence",
    "TechniqueExperimentRecord",
    "TechniquePatternEvidenceRecord",
    "CharacterSkill",
    "CharacterTechnique",
    "CombatTechniqueProfile",
    "Skill",
    "Technique",
    "TechniqueDomain",
    "TechniqueUseRecord",
    "WorldDevelopment",
    "ItemWeaponProfile",
    "ItemToolProfile",
]
