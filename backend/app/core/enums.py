from enum import StrEnum


class CharacterStatus(StrEnum):
    ALIVE = "ALIVE"
    INCAPACITATED = "INCAPACITATED"
    DEAD = "DEAD"


class CharacterXPSource(StrEnum):
    DANGER_OVERCOME = "DANGER_OVERCOME"
    SIGNIFICANT_CHALLENGE = "SIGNIFICANT_CHALLENGE"
    IMPORTANT_DISCOVERY = "IMPORTANT_DISCOVERY"
    RELEVANT_ACHIEVEMENT = "RELEVANT_ACHIEVEMENT"
    DIFFICULT_SURVIVAL = "DIFFICULT_SURVIVAL"
    IMPORTANT_OBJECTIVE = "IMPORTANT_OBJECTIVE"
    DIFFICULT_PROBLEM = "DIFFICULT_PROBLEM"
    MEANINGFUL_NEW_EXPERIENCE = "MEANINGFUL_NEW_EXPERIENCE"


class EarthProfession(StrEnum):
    CHEF = "CHEF"
    FARMER = "FARMER"
    CARPENTER = "CARPENTER"
    BLACKSMITH = "BLACKSMITH"


class ProfessionXPSource(StrEnum):
    GATHERING = "GATHERING"
    WORK = "WORK"
    CRAFTING = "CRAFTING"
    PRACTICE = "PRACTICE"


class ProfessionActivityOutcome(StrEnum):
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"
    SUCCESS = "SUCCESS"


class ClassOfferStatus(StrEnum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    DELAYED = "DELAYED"
    ACCEPTED = "ACCEPTED"


class DomainEvidenceSource(StrEnum):
    TRAINING = "TRAINING"
    TECHNIQUE_LEARNED = "TECHNIQUE_LEARNED"
    TECHNIQUE_USED = "TECHNIQUE_USED"
    EXPERIENCE = "EXPERIENCE"
    COMBAT = "COMBAT"
    STUDY = "STUDY"
    EXPERIMENTATION = "EXPERIMENTATION"
    ACHIEVEMENT = "ACHIEVEMENT"


class TechniqueType(StrEnum):
    """What powers a technique's execution — not which world system consumes
    it (combat/crafting/exploration/...); that routing is a later concern."""

    PHYSICAL = "PHYSICAL"
    MAGICAL = "MAGICAL"
    HYBRID = "HYBRID"


class TechniqueLearningState(StrEnum):
    """A character's progress toward actually being able to perform a
    technique. Absence of a CharacterTechnique row means UNKNOWN — there is
    no explicit UNKNOWN member, matching how the rest of the project treats
    missing knowledge as ignorance rather than a stored state."""

    AWARE = "AWARE"
    LEARNING = "LEARNING"
    LEARNED = "LEARNED"


class TechniqueOrigin(StrEnum):
    """How a character came to know about / learn a technique."""

    SELF_DISCOVERED = "SELF_DISCOVERED"
    TAUGHT = "TAUGHT"
    OBSERVED = "OBSERVED"
    DOCUMENTED = "DOCUMENTED"


class TechniqueMasteryTier(StrEnum):
    """How reliably a LEARNED technique can be executed — not a level, and
    never a stand-in for damage. See app.game.skills.technique_mastery."""

    UNSTABLE = "UNSTABLE"
    BASIC = "BASIC"
    PRACTICED = "PRACTICED"
    REFINED = "REFINED"
    MASTERED = "MASTERED"


class CharacterAttributeKey(StrEnum):
    STRENGTH = "STRENGTH"
    AGILITY = "AGILITY"
    VITALITY = "VITALITY"
    INTELLIGENCE = "INTELLIGENCE"
    WISDOM = "WISDOM"
    ENDURANCE = "ENDURANCE"
    LUCK = "LUCK"


class AttributeEvidenceSource(StrEnum):
    TRAINING = "TRAINING"
    PHYSICAL_EXERTION = "PHYSICAL_EXERTION"
    MENTAL_STUDY = "MENTAL_STUDY"
    PERCEPTIVE_EXPERIENCE = "PERCEPTIVE_EXPERIENCE"
    RECOVERY_CHALLENGE = "RECOVERY_CHALLENGE"
    REAL_CHALLENGE = "REAL_CHALLENGE"


class CharacterResourceKey(StrEnum):
    HP = "HP"
    MANA = "MANA"
    STAMINA = "STAMINA"


class ItemType(StrEnum):
    MISC = "MISC"
    MATERIAL = "MATERIAL"
    CURRENCY = "CURRENCY"
    AMMUNITION = "AMMUNITION"
    CONSUMABLE = "CONSUMABLE"
    WEAPON = "WEAPON"
    ARMOR = "ARMOR"
    TOOL = "TOOL"
    CONTAINER = "CONTAINER"
    QUEST = "QUEST"
    MAP = "MAP"


class ItemInstanceMode(StrEnum):
    STACKABLE = "STACKABLE"
    UNIQUE = "UNIQUE"


class ItemQuality(StrEnum):
    CRUDE = "CRUDE"
    POOR = "POOR"
    STANDARD = "STANDARD"
    GOOD = "GOOD"
    EXCELLENT = "EXCELLENT"
    MASTERWORK = "MASTERWORK"


class ItemCondition(StrEnum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    WORN = "WORN"
    DAMAGED = "DAMAGED"
    CRITICAL = "CRITICAL"
    BROKEN = "BROKEN"


class ItemWearSeverity(StrEnum):
    NEGLIGIBLE = "NEGLIGIBLE"
    LIGHT = "LIGHT"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"
    DEVASTATING = "DEVASTATING"


class ItemLocationType(StrEnum):
    UNPLACED = "UNPLACED"
    CHARACTER = "CHARACTER"
    CHARACTER_EQUIPPED = "CHARACTER_EQUIPPED"
    NPC = "NPC"
    WORLD_LOCATION = "WORLD_LOCATION"
    CONTAINER = "CONTAINER"


class ItemOwnerType(StrEnum):
    NONE = "NONE"
    CHARACTER = "CHARACTER"
    NPC = "NPC"


class EncumbranceTier(StrEnum):
    NORMAL = "NORMAL"
    LIGHTLY_ENCUMBERED = "LIGHTLY_ENCUMBERED"
    HEAVILY_ENCUMBERED = "HEAVILY_ENCUMBERED"
    OVERLOADED = "OVERLOADED"


class ItemAccessibility(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    QUICK = "QUICK"
    WORN = "WORN"
    STOWED = "STOWED"


class WeaponFamily(StrEnum):
    DAGGER = "DAGGER"
    KNIFE = "KNIFE"
    SWORD = "SWORD"
    AXE = "AXE"
    HAMMER = "HAMMER"
    MACE = "MACE"
    SPEAR = "SPEAR"
    POLEARM = "POLEARM"
    BOW = "BOW"
    CROSSBOW = "CROSSBOW"
    SLING = "SLING"
    STAFF = "STAFF"
    CLUB = "CLUB"


class PhysicalDamageProfile(StrEnum):
    SLASH = "SLASH"
    PIERCE = "PIERCE"
    BLUNT = "BLUNT"


class BodyArea(StrEnum):
    HEAD = "HEAD"
    TORSO = "TORSO"
    ARMS = "ARMS"
    HANDS = "HANDS"
    LEGS = "LEGS"
    FEET = "FEET"


class ToolCapability(StrEnum):
    HAMMERING = "HAMMERING"
    CUTTING = "CUTTING"
    MINING = "MINING"
    SAWING = "SAWING"
    COOKING = "COOKING"
    FISHING = "FISHING"
    SEWING = "SEWING"
    LOCKPICKING = "LOCKPICKING"


class WeaponReach(StrEnum):
    NORMAL = "NORMAL"
    LONG = "LONG"
    RANGED = "RANGED"


class WeaponHandRequirement(StrEnum):
    ONE_HAND = "ONE_HAND"
    ONE_OR_TWO_HANDS = "ONE_OR_TWO_HANDS"
    TWO_HANDS = "TWO_HANDS"


class CombatEncounterStatus(StrEnum):
    ACTIVE = "ACTIVE"
    VICTORY = "VICTORY"
    DEFEAT = "DEFEAT"
    FLED = "FLED"
    CANCELLED = "CANCELLED"


class CombatActorType(StrEnum):
    CHARACTER = "CHARACTER"
    NPC = "NPC"
    SIMULATED_PLAYER = "SIMULATED_PLAYER"


class CombatRangeBand(StrEnum):
    ENGAGED = "ENGAGED"
    NEAR = "NEAR"
    FAR = "FAR"
    OUT_OF_REACH = "OUT_OF_REACH"


class CombatAwareness(StrEnum):
    AWARE = "AWARE"
    SURPRISED = "SURPRISED"
    UNAWARE = "UNAWARE"


class CombatTurnStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


class CombatActionType(StrEnum):
    MELEE_ATTACK = "MELEE_ATTACK"
    RANGED_ATTACK = "RANGED_ATTACK"


class CombatActionOutcome(StrEnum):
    CRITICAL_MISS = "CRITICAL_MISS"
    MISS = "MISS"
    HIT = "HIT"
    CRITICAL_HIT = "CRITICAL_HIT"


class CombatDamageType(StrEnum):
    PHYSICAL = "PHYSICAL"
    FIRE = "FIRE"
    COLD = "COLD"
    LIGHTNING = "LIGHTNING"
    POISON = "POISON"
    ARCANE = "ARCANE"


class CombatIncapacitationStatus(StrEnum):
    CRITICAL = "CRITICAL"
    STABILIZED = "STABILIZED"
    RECOVERED = "RECOVERED"
    DEAD = "DEAD"


class EquipmentSlot(StrEnum):
    HEAD = "HEAD"
    TORSO = "TORSO"
    BODY = "TORSO"  # compatibility alias for Phase 9 callers
    LEGS = "LEGS"
    HANDS = "HANDS"
    FEET = "FEET"
    MAIN_HAND = "MAIN_HAND"
    OFF_HAND = "OFF_HAND"
    BOTH_HANDS = "BOTH_HANDS"
    BACK = "BACK"
    WAIST = "WAIST"
    ACCESSORY = "ACCESSORY"


class CombatConditionType(StrEnum):
    STUNNED = "STUNNED"
    WEAKENED = "WEAKENED"
    EXPOSED = "EXPOSED"
    GUARDED = "GUARDED"
    DODGING = "DODGING"


class CombatTacticalActionType(StrEnum):
    GUARD = "GUARD"
    DODGE = "DODGE"
    APPROACH = "APPROACH"
    RETREAT = "RETREAT"
    DISENGAGE = "DISENGAGE"
    FLEE = "FLEE"
    WAIT = "WAIT"


class CombatDecisionKind(StrEnum):
    ATTACK = "ATTACK"
    TACTICAL = "TACTICAL"


class RecoveryType(StrEnum):
    SHORT_REST = "SHORT_REST"


class ResourceGrowthSource(StrEnum):
    ATTRIBUTE_DEVELOPMENT = "ATTRIBUTE_DEVELOPMENT"
    PHYSICAL_CONDITIONING = "PHYSICAL_CONDITIONING"
    RESOURCE_EXERTION = "RESOURCE_EXERTION"
    MAGICAL_PRACTICE = "MAGICAL_PRACTICE"
    TECHNIQUE_MASTERY = "TECHNIQUE_MASTERY"
    RECOVERY_CHALLENGE = "RECOVERY_CHALLENGE"
    REAL_CHALLENGE = "REAL_CHALLENGE"
    CLASS_PATH = "CLASS_PATH"


class DiscoveryStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    RUMORED = "RUMORED"
    DISCOVERED = "DISCOVERED"
    VISITED = "VISITED"
    MAPPED = "MAPPED"


class ConnectionType(StrEnum):
    ROAD = "ROAD"
    PATH = "PATH"
    RIVER = "RIVER"
    TRAIL = "TRAIL"


class ActionIntentType(StrEnum):
    MOVE = "MOVE"
    TALK = "TALK"
    EXAMINE = "EXAMINE"
    REST = "REST"
    WAIT = "WAIT"
    SKILL_CHECK = "SKILL_CHECK"
    TECHNIQUE = "TECHNIQUE"
    EXPERIMENT = "EXPERIMENT"
    ATTACK = "ATTACK"
    DEFEND = "DEFEND"
    DODGE = "DODGE"
    APPROACH = "APPROACH"
    RETREAT = "RETREAT"
    DISENGAGE = "DISENGAGE"
    FLEE = "FLEE"
    PICK_UP = "PICK_UP"
    DROP = "DROP"
    GIVE = "GIVE"
    TAKE = "TAKE"
    EQUIP = "EQUIP"
    UNEQUIP = "UNEQUIP"
    STORE = "STORE"
    RETRIEVE = "RETRIEVE"
    MOVE_BETWEEN_CONTAINERS = "MOVE_BETWEEN_CONTAINERS"
    FREEFORM = "FREEFORM"
    UNKNOWN = "UNKNOWN"


class QuestStatus(StrEnum):
    """Shared across two distinct levels — see app.game.quests.service.

    World-level (Quest.status): whether the situation is still an open,
    unclaimed opportunity. AVAILABLE is the only non-terminal value; EXPIRED/
    CANCELLED/RESOLVED_EXTERNALLY mean the world moved on, independent of
    any one character.

    Character-level (CharacterQuest.status): one character's participation.
    NOT_STARTED is reserved for Phase 12J (quest awareness via the Knowledge
    system, distinct from participation) and unused until then.
    """

    AVAILABLE = "AVAILABLE"
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    RESOLVED_EXTERNALLY = "RESOLVED_EXTERNALLY"


class ObjectiveType(StrEnum):
    """The kind of involvement an Objective represents — a display/
    organization category, not a mechanical trigger (see
    ObjectiveTriggerType for that)."""

    INVESTIGATION = "INVESTIGATION"
    DISCOVERY = "DISCOVERY"
    DELIVERY = "DELIVERY"
    PROTECTION = "PROTECTION"
    NEGOTIATION = "NEGOTIATION"
    EXPLORATION = "EXPLORATION"
    RETRIEVAL = "RETRIEVAL"
    SURVIVAL = "SURVIVAL"
    OBSERVATION = "OBSERVATION"
    COMBAT = "COMBAT"
    CRAFTING = "CRAFTING"
    SOCIAL_INTERACTION = "SOCIAL_INTERACTION"
    WORLD_STATE_CHANGE = "WORLD_STATE_CHANGE"


class ObjectiveTriggerType(StrEnum):
    """What authoritative backend fact the Objective Evaluator
    (app.game.quests.service.evaluate_objective_trigger) watches for.
    MANUAL means no automatic evaluator exists yet for this objective —
    only an explicit complete_objective call can satisfy it. Not every
    ObjectiveType has a generic trigger wired yet; see the Phase 12B
    report for which of these have a live call site today."""

    TALK_TO_NPC = "TALK_TO_NPC"
    REACH_LOCATION = "REACH_LOCATION"
    DELIVER_ITEM = "DELIVER_ITEM"
    RETRIEVE_ITEM = "RETRIEVE_ITEM"
    DEFEAT_TARGET = "DEFEAT_TARGET"
    MANUAL = "MANUAL"


class NoticeCategory(StrEnum):
    """What kind of posting this is — not every category implies a Quest
    (Phase 12I). QUEST_REQUEST is the only one that typically carries a
    quest_id link; the rest are informational or point at other systems
    that don't exist yet (jobs/trade → Phase 14)."""

    QUEST_REQUEST = "QUEST_REQUEST"
    JOB = "JOB"
    TRADE = "TRADE"
    WANTED = "WANTED"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    WARNING = "WARNING"
    RECRUITMENT = "RECRUITMENT"
    TRAVEL = "TRAVEL"
    LOST_PROPERTY = "LOST_PROPERTY"
    MISSING_PERSON = "MISSING_PERSON"
    SERVICE_OFFER = "SERVICE_OFFER"
    RUMOR = "RUMOR"
    COMMUNITY_NOTICE = "COMMUNITY_NOTICE"


class NoticeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"
    OUTDATED = "OUTDATED"
    REMOVED = "REMOVED"


class QuestParticipationType(StrEnum):
    """How many characters may actively pursue a Quest at once (Phase
    12K). Does not by itself decide reward ownership/credit — see the
    spec's CREDIT/CONTRIBUTION section, deliberately not modeled as an
    arbitrary universal percentage."""

    OPEN = "OPEN"
    CLAIMABLE = "CLAIMABLE"
    LIMITED = "LIMITED"
    OFFICIAL_BOUNTY = "OFFICIAL_BOUNTY"


class QuestSource(StrEnum):
    """Where a Quest originated. Phase 12A only defines the vocabulary —
    ORGANIZATION_REQUEST/NOTICE_BOARD/WORLD_EVENT sources are not yet wired
    to any producer (that's Phase 12H/12I/13); SELF_DISCOVERED is the
    default for quests without a more specific origin."""

    NPC_REQUEST = "NPC_REQUEST"
    ORGANIZATION_REQUEST = "ORGANIZATION_REQUEST"
    NOTICE_BOARD = "NOTICE_BOARD"
    WORLD_EVENT = "WORLD_EVENT"
    SELF_DISCOVERED = "SELF_DISCOVERED"
    OFFICIAL_CONTRACT = "OFFICIAL_CONTRACT"
    EMERGENT_SITUATION = "EMERGENT_SITUATION"


class KnowerType(StrEnum):
    PLAYER = "PLAYER"
    NPC = "NPC"
    SIMULATED_PLAYER = "SIMULATED_PLAYER"


class MemoryOwnerType(StrEnum):
    WORLD = "WORLD"
    PLAYER = "PLAYER"
    NPC = "NPC"
    SIMULATED_PLAYER = "SIMULATED_PLAYER"


class KnowledgeCertainty(StrEnum):
    RUMOR = "RUMOR"
    BELIEVED = "BELIEVED"
    CONFIRMED = "CONFIRMED"


class GeographicKnowledgeAspect(StrEnum):
    """Phase 17A — a geographic entity (Region/Subregion/Settlement/
    Location/POI/BoundaryRoute/RegionalBoundary/...) is never known
    all-or-nothing. Each aspect becomes its own KnowledgeFact under the
    same subject (see app.game.knowledge.geography), so a character can
    know a place EXISTS long before knowing its NAME, let alone a ROUTE
    there — matching the spec's own worked example (Arven: existence →
    name/direction → distance → route, each a separate moment).
    LOCATION_PRECISION is deliberately not a member here — *how precise*
    a DIRECTION/DISTANCE/ROUTE fact is is 17B's concern, layered onto
    these same aspects rather than a tenth aspect of its own."""

    EXISTENCE = "EXISTENCE"
    NAME = "NAME"
    DIRECTION = "DIRECTION"
    DISTANCE = "DISTANCE"
    ROUTE = "ROUTE"
    DESCRIPTION = "DESCRIPTION"
    DANGERS = "DANGERS"
    SERVICES = "SERVICES"
    RELATIONSHIPS = "RELATIONSHIPS"


class GeographicPrecision(StrEnum):
    """Phase 17B — how DETAILED a geographic grant is, independent of
    KnowledgeCertainty (how SURE the knower is). A character can be
    completely confident in vague information ("everyone agrees it's
    somewhere south") or hold a very precise but doubted claim (an old,
    possibly-outdated detailed map). Ranked monotonic-upgrade-only via
    app.game.knowledge.geography.precision_rank, the same discipline
    certainty_rank already applies to certainty."""

    VAGUE = "VAGUE"
    APPROXIMATE = "APPROXIMATE"
    GOOD = "GOOD"
    PRECISE = "PRECISE"


class RumorAccuracy(StrEnum):
    """Phase 17C — the backend's own private truth about how a rumor's
    statement relates to Canon. Never exposed to the player directly
    (spec's "DO NOT SPOIL RISK" pattern, reused from Phase 16F/16H) —
    Logan only ever sees the rumor's statement text and his own
    certainty about it, never this label."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    PARTIALLY_TRUE = "PARTIALLY_TRUE"
    OUTDATED = "OUTDATED"
    MISINTERPRETED = "MISINTERPRETED"


class SimulatedPlayerArchetype(StrEnum):
    EXPLORER = "EXPLORER"
    TRAINER = "TRAINER"
    SOCIAL = "SOCIAL"
    ADVENTURER = "ADVENTURER"

class SimulatedPlayerGoalType(StrEnum):
    NONE = "NONE"
    EXPLORE_REGION = "EXPLORE_REGION"
    TRAIN_SELF = "TRAIN_SELF"
    GATHER_KNOWLEDGE = "GATHER_KNOWLEDGE"
    SEEK_DANGER = "SEEK_DANGER"

class SimulatedPlayerActivity(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESTING = "RESTING"
    TRAINING = "TRAINING"
    SOCIALIZING = "SOCIALIZING"
    WORKING = "WORKING"

class SimulatedPlayerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INCAPACITATED = "INCAPACITATED"
    DEAD = "DEAD"

class RiskTolerance(StrEnum):
    CAUTIOUS = "CAUTIOUS"
    BALANCED = "BALANCED"
    BOLD = "BOLD"


class SubregionBiome(StrEnum):
    """Phase 15D — dominant terrain character of a subregion. Distinct
    from ConnectionType/Location.type; this is a broad territorial label,
    not a single point on the map."""

    PLAINS = "PLAINS"
    FOREST = "FOREST"
    HILLS = "HILLS"
    MOUNTAINS = "MOUNTAINS"
    WETLANDS = "WETLANDS"
    RIVER_VALLEY = "RIVER_VALLEY"
    LAKE_COUNTRY = "LAKE_COUNTRY"
    COASTAL = "COASTAL"
    FRONTIER = "FRONTIER"


class DangerLevel(StrEnum):
    """Phase 15D — narrative/world danger baseline for a subregion. Not a
    direct percentage — distinct from LocationConnection.danger, which
    already drives real travel-incident math (app.game.travel.service)."""

    SAFE = "SAFE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


class SettlementType(StrEnum):
    """Phase 15F — settlement scale/purpose. Deliberately richer than a
    bare CITY/VILLAGE split (spec), but bounded — not every conceivable
    settlement archetype, just enough to give settlements a reason to
    exist and differ from each other."""

    MAJOR_CITY = "MAJOR_CITY"
    CITY = "CITY"
    TOWN = "TOWN"
    VILLAGE = "VILLAGE"
    HAMLET = "HAMLET"
    ISOLATED_SETTLEMENT = "ISOLATED_SETTLEMENT"
    FORTRESS_SETTLEMENT = "FORTRESS_SETTLEMENT"
    MINING_SETTLEMENT = "MINING_SETTLEMENT"
    RELIGIOUS_SETTLEMENT = "RELIGIOUS_SETTLEMENT"
    TRADE_SETTLEMENT = "TRADE_SETTLEMENT"


class ThreatType(StrEnum):
    """Phase 15L — broad ecology/threat category for a subregion.
    Population/habitat abstraction, never individual creature instances
    (spec: do not generate every animal at save creation)."""

    WOLVES = "WOLVES"
    BOARS = "BOARS"
    BANDITS = "BANDITS"
    MONSTERS = "MONSTERS"
    HAZARDOUS_TERRAIN = "HAZARDOUS_TERRAIN"
    MAGICAL_ANOMALY = "MAGICAL_ANOMALY"


class ThreatIntensity(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class PopulationDensity(StrEnum):
    """Phase 15D — how densely a subregion is settled, independent of any
    single settlement's own size (see Phase 15F)."""

    SPARSE = "SPARSE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    DENSE = "DENSE"

class SimulatedPlayerGroupStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISSOLVED = "DISSOLVED"


class RegionMaterializationRequestSource(StrEnum):
    """Phase 16A — who/what determined that a neighboring Region needs to
    exist. Mirrors the trigger categories from the Phase 16 spec; the
    protagonist is deliberately not privileged over any other source."""

    PLAYER_EXPLORATION = "PLAYER_EXPLORATION"
    SIMULATED_CHARACTER = "SIMULATED_CHARACTER"
    ORGANIZATION = "ORGANIZATION"
    MILITARY_POLITICAL = "MILITARY_POLITICAL"
    QUEST_EVENT = "QUEST_EVENT"
    ECONOMY = "ECONOMY"
    WORLD_HISTORY = "WORLD_HISTORY"


class RegionMaterializationRequestStatus(StrEnum):
    """Phase 16A — a request never generates a Region by itself (that is
    16I+); this only tracks whether one still needs to happen."""

    PENDING = "PENDING"
    FULFILLED = "FULFILLED"
    REJECTED = "REJECTED"


class Season(StrEnum):
    """Phase 16E — derived purely from WorldTime.month (already a real
    12-month calendar, see app.game.time.clock.season_for_month), never
    its own stored state."""

    SPRING = "SPRING"
    SUMMER = "SUMMER"
    AUTUMN = "AUTUMN"
    WINTER = "WINTER"


class CrossingFeasibilityVerdict(StrEnum):
    """Phase 16F — always advisory, never a gate. None of these values
    block travel; app.game.world.crossing.evaluate_crossing_feasibility
    is a preview a character (or the narrator) can consult, not a
    CAN_CROSS boolean (spec explicitly rejects that shape)."""

    FEASIBLE = "FEASIBLE"
    POSSIBLE_BUT_DANGEROUS = "POSSIBLE_BUT_DANGEROUS"
    LIKELY_TO_FAIL = "LIKELY_TO_FAIL"


class RouteAccessibility(StrEnum):
    """Phase 16E/16F — always derived on demand from a route + current
    season (see app.game.world.boundaries.route_accessibility_for_season),
    never stored as a permanent boolean (spec)."""

    OPEN = "OPEN"
    RISKY = "RISKY"
    NEARLY_IMPASSABLE = "NEARLY_IMPASSABLE"


class BoundaryBarrierCategory(StrEnum):
    """Phase 16C — what makes a RegionalBoundary hard to cross. A single
    boundary may combine several (spec's "COMBINED BARRIERS" — difficulty
    comes from the combination, never an arbitrary difficulty number)."""

    GEOGRAPHICAL = "GEOGRAPHICAL"
    CLIMATIC = "CLIMATIC"
    ECOLOGICAL = "ECOLOGICAL"
    POLITICAL = "POLITICAL"
    LOGISTICAL = "LOGISTICAL"
    MAGICAL = "MAGICAL"


class EventType(StrEnum):
    CAMPAIGN_CREATED = "CAMPAIGN_CREATED"
    WORLD_STARTED = "WORLD_STARTED"
    STORY_EXCHANGE = "STORY_EXCHANGE"
    CHARACTER_CREATED = "CHARACTER_CREATED"
    PLAYER_MOVED = "PLAYER_MOVED"
    TRAVEL_INCIDENT = "TRAVEL_INCIDENT"
    PLAYER_MET_NPC = "PLAYER_MET_NPC"
    PLAYER_TALKED_TO_NPC = "PLAYER_TALKED_TO_NPC"
    PLAYER_MET_SIMULATED_PLAYER = "PLAYER_MET_SIMULATED_PLAYER"
    PLAYER_TALKED_TO_SIMULATED_PLAYER = "PLAYER_TALKED_TO_SIMULATED_PLAYER"
    PLAYER_GAINED_ITEM = "PLAYER_GAINED_ITEM"
    PLAYER_LOST_ITEM = "PLAYER_LOST_ITEM"
    ITEM_LOCATION_CHANGED = "ITEM_LOCATION_CHANGED"
    ITEM_OWNERSHIP_CHANGED = "ITEM_OWNERSHIP_CHANGED"
    ITEM_EQUIPPED = "ITEM_EQUIPPED"
    ITEM_UNEQUIPPED = "ITEM_UNEQUIPPED"
    ITEM_WEAR_APPLIED = "ITEM_WEAR_APPLIED"
    ITEM_BROKEN = "ITEM_BROKEN"
    ITEM_INTERACTION_RESOLVED = "ITEM_INTERACTION_RESOLVED"
    PLAYER_RESTED = "PLAYER_RESTED"
    PLAYER_GAINED_XP = "PLAYER_GAINED_XP"
    PLAYER_LEVELED_UP = "PLAYER_LEVELED_UP"
    PLAYER_GAINED_PROFESSION_XP = "PLAYER_GAINED_PROFESSION_XP"
    PLAYER_PROFESSION_LEVELED_UP = "PLAYER_PROFESSION_LEVELED_UP"
    PLAYER_COMPLETED_PROFESSION_ACTIVITY = "PLAYER_COMPLETED_PROFESSION_ACTIVITY"
    PLAYER_CLASS_OFFERED = "PLAYER_CLASS_OFFERED"
    PLAYER_CLASS_OFFER_DELAYED = "PLAYER_CLASS_OFFER_DELAYED"
    PLAYER_CLASS_ACCEPTED = "PLAYER_CLASS_ACCEPTED"
    PLAYER_ATTRIBUTE_INCREASED = "PLAYER_ATTRIBUTE_INCREASED"
    PLAYER_RESOURCE_MAX_INCREASED = "PLAYER_RESOURCE_MAX_INCREASED"
    PLAYER_DIED = "PLAYER_DIED"
    ACTION_CHECK_RESULT = "ACTION_CHECK_RESULT"
    COMBAT_STARTED = "COMBAT_STARTED"
    COMBAT_PARTICIPANT_JOINED = "COMBAT_PARTICIPANT_JOINED"
    COMBAT_PARTICIPANT_LEFT = "COMBAT_PARTICIPANT_LEFT"
    COMBAT_INITIATIVE_ROLLED = "COMBAT_INITIATIVE_ROLLED"
    COMBAT_TURN_ADVANCED = "COMBAT_TURN_ADVANCED"
    COMBAT_ACTION_RESOLVED = "COMBAT_ACTION_RESOLVED"
    COMBAT_DAMAGE_APPLIED = "COMBAT_DAMAGE_APPLIED"
    COMBAT_PARTICIPANT_INCAPACITATED = "COMBAT_PARTICIPANT_INCAPACITATED"
    COMBAT_CRITICAL_CHECK_RESOLVED = "COMBAT_CRITICAL_CHECK_RESOLVED"
    COMBAT_PARTICIPANT_STABILIZED = "COMBAT_PARTICIPANT_STABILIZED"
    COMBAT_PARTICIPANT_RECOVERED = "COMBAT_PARTICIPANT_RECOVERED"
    COMBAT_RESOURCE_SPENT = "COMBAT_RESOURCE_SPENT"
    COMBAT_CONDITION_APPLIED = "COMBAT_CONDITION_APPLIED"
    COMBAT_CONDITION_TRIGGERED = "COMBAT_CONDITION_TRIGGERED"
    COMBAT_CONDITION_EXPIRED = "COMBAT_CONDITION_EXPIRED"
    COMBAT_CONDITION_REMOVED = "COMBAT_CONDITION_REMOVED"
    COMBAT_TACTICAL_ACTION_RESOLVED = "COMBAT_TACTICAL_ACTION_RESOLVED"
    COMBAT_AUTONOMOUS_DECISION_RESOLVED = "COMBAT_AUTONOMOUS_DECISION_RESOLVED"
    COMBAT_ENDED = "COMBAT_ENDED"
    QUEST_STARTED = "QUEST_STARTED"
    QUEST_OBJECTIVE_COMPLETED = "QUEST_OBJECTIVE_COMPLETED"
    QUEST_COMPLETED = "QUEST_COMPLETED"
    QUEST_FAILED = "QUEST_FAILED"
    QUEST_CANCELLED = "QUEST_CANCELLED"
    QUEST_EXPIRED = "QUEST_EXPIRED"
    QUEST_RESOLVED_EXTERNALLY = "QUEST_RESOLVED_EXTERNALLY"
    NOTICE_POSTED = "NOTICE_POSTED"
    NOTICE_WITHDRAWN = "NOTICE_WITHDRAWN"
    NOTICE_EXPIRED = "NOTICE_EXPIRED"
    NOTICE_UPDATED = "NOTICE_UPDATED"
    GROUP_CREATED = "GROUP_CREATED"
    GROUP_MEMBER_JOINED = "GROUP_MEMBER_JOINED"
    GROUP_MEMBER_LEFT = "GROUP_MEMBER_LEFT"
    GROUP_DISBANDED = "GROUP_DISBANDED"
    GROUP_INVITE_SENT = "GROUP_INVITE_SENT"
    GROUP_INVITE_ACCEPTED = "GROUP_INVITE_ACCEPTED"
    GROUP_INVITE_DECLINED = "GROUP_INVITE_DECLINED"
    GROUP_INVITE_WITHDRAWN = "GROUP_INVITE_WITHDRAWN"
    GROUP_LEADERSHIP_CHANGED = "GROUP_LEADERSHIP_CHANGED"
    ORGANIZATION_CREATED = "ORGANIZATION_CREATED"
    ORGANIZATION_STATUS_CHANGED = "ORGANIZATION_STATUS_CHANGED"
    ORGANIZATION_FOUNDED_FROM_GROUP = "ORGANIZATION_FOUNDED_FROM_GROUP"
    ORGANIZATION_FORMALLY_RECOGNIZED = "ORGANIZATION_FORMALLY_RECOGNIZED"
    ORGANIZATION_ROLE_CREATED = "ORGANIZATION_ROLE_CREATED"
    ORGANIZATION_MEMBER_JOINED = "ORGANIZATION_MEMBER_JOINED"
    ORGANIZATION_MEMBER_STATUS_CHANGED = "ORGANIZATION_MEMBER_STATUS_CHANGED"
    ORGANIZATION_MEMBER_ROLE_CHANGED = "ORGANIZATION_MEMBER_ROLE_CHANGED"
    ORGANIZATION_REPUTATION_CHANGED = "ORGANIZATION_REPUTATION_CHANGED"
    ORGANIZATION_RELATION_ESTABLISHED = "ORGANIZATION_RELATION_ESTABLISHED"
    ORGANIZATION_RELATION_ENDED = "ORGANIZATION_RELATION_ENDED"
    ORGANIZATION_GOAL_CREATED = "ORGANIZATION_GOAL_CREATED"
    ORGANIZATION_GOAL_STATUS_CHANGED = "ORGANIZATION_GOAL_STATUS_CHANGED"
    ORGANIZATION_NEED_CREATED = "ORGANIZATION_NEED_CREATED"
    ORGANIZATION_NEED_STATUS_CHANGED = "ORGANIZATION_NEED_STATUS_CHANGED"
    ORGANIZATION_ASSET_ASSIGNED = "ORGANIZATION_ASSET_ASSIGNED"
    ORGANIZATION_ASSET_UNASSIGNED = "ORGANIZATION_ASSET_UNASSIGNED"
    ORGANIZATION_FUNDS_CHANGED = "ORGANIZATION_FUNDS_CHANGED"
    ORGANIZATION_ACTION_RESOLVED = "ORGANIZATION_ACTION_RESOLVED"
    ORGANIZATION_CONFLICT_STARTED = "ORGANIZATION_CONFLICT_STARTED"
    ORGANIZATION_CONFLICT_STATUS_CHANGED = "ORGANIZATION_CONFLICT_STATUS_CHANGED"
    CURRENCY_DEPOSITED = "CURRENCY_DEPOSITED"
    CURRENCY_WITHDRAWN = "CURRENCY_WITHDRAWN"
    CURRENCY_TRANSFERRED = "CURRENCY_TRANSFERRED"
    TRANSACTION_COMPLETED = "TRANSACTION_COMPLETED"
    JOB_CREATED = "JOB_CREATED"
    JOB_APPLICATION_SUBMITTED = "JOB_APPLICATION_SUBMITTED"
    JOB_APPLICATION_RESOLVED = "JOB_APPLICATION_RESOLVED"
    JOB_EMPLOYMENT_ENDED = "JOB_EMPLOYMENT_ENDED"
    WAGE_PAID = "WAGE_PAID"
    PRODUCTION_COMPLETED = "PRODUCTION_COMPLETED"
    SHOP_STOCKED = "SHOP_STOCKED"
    SHOP_UNSTOCKED = "SHOP_UNSTOCKED"
    SHOP_TILL_CHANGED = "SHOP_TILL_CHANGED"
    SUPPLY_CHANGED = "SUPPLY_CHANGED"
    BUSINESS_FOUNDED = "BUSINESS_FOUNDED"
    BUSINESS_CLOSED = "BUSINESS_CLOSED"
    BUSINESS_OPERATOR_CHANGED = "BUSINESS_OPERATOR_CHANGED"
    BUSINESS_FUNDS_CHANGED = "BUSINESS_FUNDS_CHANGED"
    ECONOMIC_DISRUPTION_APPLIED = "ECONOMIC_DISRUPTION_APPLIED"
    NPC_DIED = "NPC_DIED"
    REGION_DISCOVERED = "REGION_DISCOVERED"
    LOCATION_DISCOVERED = "LOCATION_DISCOVERED"
    LOCATION_VISITED = "LOCATION_VISITED"
    CONNECTION_DISCOVERED = "CONNECTION_DISCOVERED"
    BOSS_DISCOVERED = "BOSS_DISCOVERED"
    BOSS_DEFEATED = "BOSS_DEFEATED"
    NEW_TECHNIQUE_CREATED = "NEW_TECHNIQUE_CREATED"
    TECHNIQUE_AWARENESS_GAINED = "TECHNIQUE_AWARENESS_GAINED"
    TECHNIQUE_LEARNING_STARTED = "TECHNIQUE_LEARNING_STARTED"
    TECHNIQUE_LEARNED = "TECHNIQUE_LEARNED"
    TECHNIQUE_RECOGNIZED = "TECHNIQUE_RECOGNIZED"
    WORLD_TIME_ADVANCED = "WORLD_TIME_ADVANCED"
    WORLD_DEVELOPMENT_CREATED = "WORLD_DEVELOPMENT_CREATED"
    WORLD_DEVELOPMENT_UPDATED = "WORLD_DEVELOPMENT_UPDATED"
    WORLD_DEVELOPMENT_COMPLETED = "WORLD_DEVELOPMENT_COMPLETED"
    SIMULATED_PLAYER_TRAVEL_STARTED = "SIMULATED_PLAYER_TRAVEL_STARTED"
    SIMULATED_PLAYER_MOVED = "SIMULATED_PLAYER_MOVED"
    SIMULATED_PLAYER_TRAINED = "SIMULATED_PLAYER_TRAINED"
    SIMULATED_PLAYER_GAINED_XP = "SIMULATED_PLAYER_GAINED_XP"
    SIMULATED_PLAYER_LEVELED_UP = "SIMULATED_PLAYER_LEVELED_UP"
    SIMULATED_PLAYER_GOAL_COMPLETED = "SIMULATED_PLAYER_GOAL_COMPLETED"
    SIMULATED_PLAYER_GOAL_ASSIGNED = "SIMULATED_PLAYER_GOAL_ASSIGNED"
    SIMULATED_PLAYER_DIED = "SIMULATED_PLAYER_DIED"
    SIMULATED_PLAYER_GROUP_CREATED = "SIMULATED_PLAYER_GROUP_CREATED"
    SIMULATED_PLAYER_GROUP_JOINED = "SIMULATED_PLAYER_GROUP_JOINED"
    SIMULATED_PLAYER_GROUP_LEFT = "SIMULATED_PLAYER_GROUP_LEFT"
    SIMULATED_PLAYER_GROUP_DISSOLVED = "SIMULATED_PLAYER_GROUP_DISSOLVED"
    SIMULATED_PLAYER_GROUP_TRAVEL_STARTED = "SIMULATED_PLAYER_GROUP_TRAVEL_STARTED"
    SIMULATED_PLAYER_WORLD_ARRIVAL = "SIMULATED_PLAYER_WORLD_ARRIVAL"
    RELATIONSHIP_CHANGED = "RELATIONSHIP_CHANGED"
    KNOWLEDGE_PROPAGATED = "KNOWLEDGE_PROPAGATED"
    SOCIAL_KNOWLEDGE_OPPORTUNITY_RESOLVED = (
        "SOCIAL_KNOWLEDGE_OPPORTUNITY_RESOLVED"
    )
    REGION_MATERIALIZATION_REQUESTED = "REGION_MATERIALIZATION_REQUESTED"
    REGION_MATERIALIZATION_FULFILLED = "REGION_MATERIALIZATION_FULFILLED"
    REGION_MATERIALIZATION_REJECTED = "REGION_MATERIALIZATION_REJECTED"
    EXPLORATION_ATTEMPTED = "EXPLORATION_ATTEMPTED"

class TravelPace(StrEnum):
    SLOW = "SLOW"
    NORMAL = "NORMAL"
    FAST = "FAST"

class NPCActivity(StrEnum):
    RESTING = "RESTING"
    WORKING = "WORKING"
    AVAILABLE = "AVAILABLE"
    
class WorldDevelopmentType(StrEnum):
    CONSTRUCTION = "CONSTRUCTION"

class WorldDevelopmentStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class TravelIncidentKind(StrEnum):
    DELAY = "DELAY"
    FATIGUE = "FATIGUE"


class GroupType(StrEnum):
    """Phase 13A — a Group is smaller and often temporary, unlike an
    Organization (Phase 13C+). member_type on GroupMember reuses
    CombatActorType (CHARACTER/NPC/SIMULATED_PLAYER) — the same "what kind
    of living actor" vocabulary CombatParticipant already established,
    rather than a third near-duplicate enum."""

    TRAVEL = "TRAVEL"
    EXPEDITION = "EXPEDITION"
    ESCORT = "ESCORT"
    WORK_CREW = "WORK_CREW"
    HUNTING_PARTY = "HUNTING_PARTY"
    TEMPORARY_ALLIANCE = "TEMPORARY_ALLIANCE"
    SEARCH_PARTY = "SEARCH_PARTY"
    OTHER = "OTHER"


class GroupStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISBANDED = "DISBANDED"
    COMPLETED_PURPOSE = "COMPLETED_PURPOSE"
    ABANDONED = "ABANDONED"


class OrganizationType(StrEnum):
    """Phase 13C — one general model for every kind of persistent social
    entity, per the spec's explicit instruction not to build separate
    tables (GuildTable, ChurchTable, ...) per type."""

    GUILD = "GUILD"
    COMMERCIAL = "COMMERCIAL"
    RELIGIOUS = "RELIGIOUS"
    MILITARY = "MILITARY"
    POLITICAL = "POLITICAL"
    CRIMINAL = "CRIMINAL"
    ACADEMIC = "ACADEMIC"
    COMMUNITY = "COMMUNITY"
    MERCENARY = "MERCENARY"
    ARTISAN = "ARTISAN"
    OTHER = "OTHER"


class OrganizationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISBANDED = "DISBANDED"
    DESTROYED = "DESTROYED"
    DORMANT = "DORMANT"
    ILLEGAL = "ILLEGAL"
    UNDERGROUND = "UNDERGROUND"


class OrganizationOrigin(StrEnum):
    """Phase 13D/13E — did this organization predate transported people
    arriving, or did transported people found it? Two different creation
    paths (app.game.organizations.native / .transported), same
    Organization model."""

    NATIVE = "NATIVE"
    TRANSPORTED_CREATED = "TRANSPORTED_CREATED"


class TransportedPeopleStance(StrEnum):
    """Phase 13D — a native organization's own disposition toward
    transported people. Deliberately a per-organization field, not a
    single hardcoded universal attitude — two native organizations may
    (and should be free to) hold different stances."""

    WELCOMING = "WELCOMING"
    FEARFUL = "FEARFUL"
    EXPLOITATIVE = "EXPLOITATIVE"
    RECRUITING = "RECRUITING"
    INDIFFERENT = "INDIFFERENT"
    OPPOSED = "OPPOSED"
    STUDYING = "STUDYING"


class OrganizationFormality(StrEnum):
    """Phase 13E — an organization may exist informally, before (or
    without ever) being legally recognized; existence itself never
    requires formal registration. Deliberately only these two values —
    the spec's other two candidates (ILLEGAL, SECRET) already exist as
    orthogonal fields (OrganizationStatus.ILLEGAL, OrganizationVisibility
    .SECRET, both Phase 13C) and are not duplicated here."""

    INFORMAL = "INFORMAL"
    FORMALLY_RECOGNIZED = "FORMALLY_RECOGNIZED"


class OrganizationVisibility(StrEnum):
    """Whether the organization's existence itself is publicly known —
    not the same axis as legal recognition (Phase 13E's INFORMAL /
    FORMALLY_RECOGNIZED, deliberately not built yet)."""

    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    SECRET = "SECRET"


class OrganizationReputationCategory(StrEnum):
    """Phase 13G — derived from accumulated, explainable reputation
    records (see app.game.organizations.reputation), never a bare
    -100..100 number treated as the only source of truth. A raw score
    exists internally for convenience, but this category plus the full
    reason history is what's actually authoritative."""

    HOSTILE = "HOSTILE"
    DISTRUSTED = "DISTRUSTED"
    NEUTRAL = "NEUTRAL"
    RELIABLE = "RELIABLE"
    TRUSTED = "TRUSTED"


class OrganizationGoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ACHIEVED = "ACHIEVED"
    ABANDONED = "ABANDONED"


class OrganizationNeedStatus(StrEnum):
    OPEN = "OPEN"
    FULFILLED = "FULFILLED"
    ABANDONED = "ABANDONED"


class OrganizationNeedCategory(StrEnum):
    """Phase 13I — GOALS != NEEDS: a goal is qualitative and free text
    (see OrganizationGoal.description); a need additionally carries a
    structured category, since Phase 13M will need to route needs toward
    notices/jobs/purchases by kind."""

    MONEY = "MONEY"
    LABOR = "LABOR"
    FOOD = "FOOD"
    MEDICINE = "MEDICINE"
    WEAPONS = "WEAPONS"
    MATERIALS = "MATERIALS"
    INFORMATION = "INFORMATION"
    SKILLED_MEMBERS = "SKILLED_MEMBERS"
    GUARDS = "GUARDS"
    TRANSPORT = "TRANSPORT"
    POLITICAL_SUPPORT = "POLITICAL_SUPPORT"
    OTHER = "OTHER"


class OrganizationActionType(StrEnum):
    """Phase 13K — the spec lists 17 possible organization actions but
    explicitly says not to implement every one immediately. These are
    the ones with a real backend mechanism today (RECRUIT/EXPEL/PROMOTE
    reuse Phase 13F directly; PUBLISH_NOTICE will reuse Phase 12 once
    13M wires it); OTHER covers any validated-but-not-yet-mechanized
    proposal, keeping the architecture extensible without needing a
    migration for every new verb."""

    RECRUIT_MEMBER = "RECRUIT_MEMBER"
    EXPEL_MEMBER = "EXPEL_MEMBER"
    PROMOTE_MEMBER = "PROMOTE_MEMBER"
    PUBLISH_NOTICE = "PUBLISH_NOTICE"
    FORM_ALLIANCE = "FORM_ALLIANCE"
    DECLARE_HOSTILITY = "DECLARE_HOSTILITY"
    OTHER = "OTHER"


class SettlementWealthBand(StrEnum):
    """Phase 14I — broad economic character, NOT a price multiplier (the
    spec is explicit: don't make this an arbitrary universal multiplier).
    Consumed as a descriptive/liquidity signal — see
    app.game.economy.local_economy.typical_merchant_liquidity_bronze and
    gold_circulates_normally."""

    POOR = "POOR"
    MODEST = "MODEST"
    PROSPEROUS = "PROSPEROUS"
    WEALTHY = "WEALTHY"


class BusinessType(StrEnum):
    TAVERN = "TAVERN"
    SHOP = "SHOP"
    WORKSHOP = "WORKSHOP"
    FARM = "FARM"
    SMITHY = "SMITHY"
    CARAVAN_COMPANY = "CARAVAN_COMPANY"
    TRADING_COMPANY = "TRADING_COMPANY"
    INN = "INN"
    RESTAURANT = "RESTAURANT"
    SERVICE = "SERVICE"
    OTHER = "OTHER"


class BusinessStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class ShopStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class EconomicActorType(StrEnum):
    """Phase 14 — who can participate economically. A superset of
    CombatActorType (CHARACTER/NPC/SIMULATED_PLAYER): Organizations
    (Phase 13) and Businesses (Phase 14J/14K) are real economic actors
    too (employers, owners of money) but are not a CombatActorType. Used
    for Job employers and Business owners; workers/applicants stay
    CombatActorType since only living actors work a job.
    withdraw_from_actor/deposit_to_actor (Phase 14J) is where each of
    these actually keeps its money: Organization.treasury, Business.
    till_bronze, or a CurrencyHolding."""

    CHARACTER = "CHARACTER"
    NPC = "NPC"
    SIMULATED_PLAYER = "SIMULATED_PLAYER"
    ORGANIZATION = "ORGANIZATION"
    BUSINESS = "BUSINESS"


class JobStatus(StrEnum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    CLOSED = "CLOSED"


class JobPaymentFrequency(StrEnum):
    PER_TASK = "PER_TASK"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    PER_UNIT = "PER_UNIT"
    COMMISSION = "COMMISSION"
    CONTRACT = "CONTRACT"
    SHARE = "SHARE"


class JobApplicationStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    ENDED = "ENDED"


class OrganizationConflictType(StrEnum):
    RIVALRY = "RIVALRY"
    TRADE_DISPUTE = "TRADE_DISPUTE"
    TERRITORIAL_DISPUTE = "TERRITORIAL_DISPUTE"
    POLITICAL_DISPUTE = "POLITICAL_DISPUTE"
    RELIGIOUS_CONFLICT = "RELIGIOUS_CONFLICT"
    OPEN_HOSTILITY = "OPEN_HOSTILITY"
    WAR = "WAR"
    INTERNAL_SCHISM = "INTERNAL_SCHISM"


class OrganizationConflictStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    RESOLVED = "RESOLVED"


class OrganizationRelationType(StrEnum):
    """Phase 13H — deliberately not one exclusive enum per organization
    pair: multiple OrganizationRelation rows of different types may
    coexist between the same two organizations (e.g. TRADE_PARTNER and
    COMPETITOR at once) — see app.game.organizations.relations."""

    ALLIED = "ALLIED"
    FRIENDLY = "FRIENDLY"
    NEUTRAL = "NEUTRAL"
    RIVAL = "RIVAL"
    HOSTILE = "HOSTILE"
    AT_WAR = "AT_WAR"
    TRADE_PARTNER = "TRADE_PARTNER"
    SUBORDINATE = "SUBORDINATE"
    PROTECTOR = "PROTECTOR"
    COMPETITOR = "COMPETITOR"


class OrganizationRelationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class OrganizationMembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPELLED = "EXPELLED"
    LEFT = "LEFT"
    DECEASED = "DECEASED"


class OrganizationPermission(StrEnum):
    """Phase 13F — the vocabulary a role's permission list may draw from.
    Nothing mechanically checks these yet (no system consumes them until
    Phase 13K Organization Actions and beyond) — this exists so
    OrganizationRole.permissions_json has a defined, extensible
    vocabulary instead of arbitrary free strings."""

    RECRUIT_MEMBER = "RECRUIT_MEMBER"
    REMOVE_MEMBER = "REMOVE_MEMBER"
    PROMOTE_MEMBER = "PROMOTE_MEMBER"
    DEMOTE_MEMBER = "DEMOTE_MEMBER"
    MANAGE_RESOURCES = "MANAGE_RESOURCES"
    ACCESS_STORAGE = "ACCESS_STORAGE"
    CREATE_NOTICE = "CREATE_NOTICE"
    CREATE_CONTRACT = "CREATE_CONTRACT"
    MANAGE_MONEY = "MANAGE_MONEY"
    REPRESENT_ORGANIZATION = "REPRESENT_ORGANIZATION"
    NEGOTIATE = "NEGOTIATE"
    MANAGE_ASSETS = "MANAGE_ASSETS"
    ASSIGN_TASKS = "ASSIGN_TASKS"


class GroupInviteStatus(StrEnum):
    """Phase 13B — an invite is never assumed accepted. Someone proposing
    to travel together does not create membership by itself; only
    accept_invite (an explicit decision by the invited party) does."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
