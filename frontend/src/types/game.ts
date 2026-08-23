export interface Campaign {
  id: string;
  name: string;
  created_at: string;
}

export interface CampaignWithCharacters extends Campaign {
  characters: Character[];
}

export interface Character {
  id: string;
  name: string;
  background: string | null;
  profession_affinity_key: string | null;
  active_class_id: string | null;
  level: number;
  xp: number;
  hp_current: number;
  hp_max: number;
  mana_current: number;
  mana_max: number;
  stamina_current: number;
  stamina_max: number;
  status: "ALIVE" | "INCAPACITATED" | "DEAD";
  region_id: string | null;
  location_id: string | null;
}

export interface RegionSummary {
  id: string;
  name: string | null;
  description: string | null;
  discovery_status: string;
}

export interface LocationSummary {
  id: string;
  name: string | null;
  type: string;
  description: string | null;
  discovery_status: string;
}

export interface WorldTime {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

export interface NearbyNPC {
  id: string;
  name: string;
  role: string;
  activity: string;
}

export interface NearbySimulatedPlayer {
  id: string;
  name: string;
  level: number;
  xp: number;
  archetype: string;
  risk_tolerance: "CAUTIOUS" | "BALANCED" | "BOLD";
  goal: string;
  group_id: string | null;
}

export interface ActiveQuestSummary {
  quest_id: string;
  name: string;
  status: string;
}

export interface CombatParticipantSummary {
  participant_id: string;
  actor_type: "CHARACTER" | "NPC" | "SIMULATED_PLAYER";
  actor_id: string;
  name: string;
  side_key: string;
  range_band: "ENGAGED" | "NEAR" | "FAR" | "OUT_OF_REACH";
  hp_current: number;
  hp_max: number;
  is_current_turn: boolean;
}

export interface CombatEncounterSummary {
  encounter_id: string;
  status: "ACTIVE" | "VICTORY" | "DEFEAT" | "FLED" | "CANCELLED";
  round_number: number;
  participants: CombatParticipantSummary[];
}

export interface GameState {
  character: Character;
  region: RegionSummary | null;
  location: LocationSummary | null;
  world_time: WorldTime | null;
  nearby_npcs: NearbyNPC[];
  nearby_simulated_players: NearbySimulatedPlayer[];
  active_quests: ActiveQuestSummary[];
  inventory: SystemInventory;
  active_encounter: CombatEncounterSummary | null;
  opening_narrative: string | null;
  opening_narrator_unavailable: boolean;
}

export interface ActionResponse {
  narrative: string;
  narrator_unavailable: boolean;
  mechanical_summary: string;
  intent_type: string;
  warnings: string[];
  state: GameState;
}

export interface WorldStartResponse {
  narrative: string;
  narrator_unavailable: boolean;
  state: GameState;
}

export interface StoryEntry {
  id: string;
  kind: "player" | "narrator";
  text: string;
  created_at: string;
}

export interface StoryLog {
  entries: StoryEntry[];
}

export interface CharacterAttribute {
  key: string;
  name: string;
  value: number;
}

export interface CharacterSkill {
  name: string;
  mastery: number;
}

export interface CharacterProfession {
  key: string;
  name: string;
  level: number;
  xp: number;
}

export interface CharacterClassDefinition {
  id: string;
  name: string;
  description: string;
}

export interface CharacterClassOffer {
  id: string;
  status: "AVAILABLE" | "DELAYED";
  class_definition: CharacterClassDefinition;
}

export interface CharacterTechnique {
  id: string;
  name: string;
  description: string;
  type: string;
  mastery: string;
}

export interface CharacterSheet {
  character: Character;
  attributes: CharacterAttribute[];
  professions: CharacterProfession[];
  active_class: CharacterClassDefinition | null;
  class_offers: CharacterClassOffer[];
  skills: CharacterSkill[];
  techniques: CharacterTechnique[];
}

export interface SystemXPProgress {
  level: number;
  current: number;
  to_next_level: number;
}

export interface SystemResourceProgress {
  key: "HP" | "MANA" | "STAMINA";
  name: string;
  current: number;
  maximum: number;
}

export interface SystemProgression {
  character_id: string;
  character_name: string;
  character_xp: SystemXPProgress;
  professions: CharacterProfession[];
  active_class: CharacterClassDefinition | null;
  class_offers: CharacterClassOffer[];
  attributes: CharacterAttribute[];
  resources: SystemResourceProgress[];
}

export interface InventoryItem {
  item_instance_id: string;
  item_id: string;
  name: string;
  type: string;
  quantity: number;
  quality: ItemQuality;
  condition: ItemCondition | null;
  material: ItemMaterial | null;
  container?: ContainerProfile | null;
  contained_in_item_instance_id?: string | null;
  contained_in_name?: string | null;
  equipped: boolean;
  unit_weight: number;
  total_weight: number;
  equipped_slot: EquipmentSlot | null;
  accessibility: ItemAccessibility;
  allowed_slots: EquipmentSlot[];
  weapon: WeaponProfile | null;
  armor: ArmorProfile | null;
  tool: ToolProfile | null;
}

export interface SystemInventoryItem {
  item_instance_id: string;
  name: string;
  type: string;
  quantity: number;
  quality: ItemQuality;
  condition: ItemCondition | null;
  material_name: string | null;
  equipped_slot: EquipmentSlot | null;
  accessibility: ItemAccessibility;
  contained_in_name: string | null;
}

export interface SystemInventory {
  items: SystemInventoryItem[];
  total_weight: number;
  carrying_capacity: number;
  encumbrance: EncumbranceTier;
}

export type ItemQuality =
  | "CRUDE"
  | "POOR"
  | "STANDARD"
  | "GOOD"
  | "EXCELLENT"
  | "MASTERWORK";
export type ItemCondition =
  | "EXCELLENT"
  | "GOOD"
  | "WORN"
  | "DAMAGED"
  | "CRITICAL"
  | "BROKEN";
export interface ItemMaterial {
  key: string;
  name: string;
}

export interface ContainerProfile {
  weight_capacity: number;
  content_weight: number;
}

export interface WeaponProfile {
  family: WeaponFamily;
  damage_profiles: PhysicalDamageProfile[];
  reach: WeaponReach;
  hand_requirement: WeaponHandRequirement;
}

export type WeaponFamily =
  | "DAGGER"
  | "KNIFE"
  | "SWORD"
  | "AXE"
  | "HAMMER"
  | "MACE"
  | "SPEAR"
  | "POLEARM"
  | "BOW"
  | "CROSSBOW"
  | "SLING"
  | "STAFF"
  | "CLUB";

export type PhysicalDamageProfile = "SLASH" | "PIERCE" | "BLUNT";
export type BodyArea = "HEAD" | "TORSO" | "ARMS" | "HANDS" | "LEGS" | "FEET";
export interface ArmorProfile {
  coverage: BodyArea[];
  physical_protections: Partial<Record<PhysicalDamageProfile, number>>;
}
export type ToolCapability =
  | "HAMMERING"
  | "CUTTING"
  | "MINING"
  | "SAWING"
  | "COOKING"
  | "FISHING"
  | "SEWING"
  | "LOCKPICKING";
export interface ToolProfile {
  capabilities: ToolCapability[];
}
export type WeaponReach = "NORMAL" | "LONG" | "RANGED";
export type WeaponHandRequirement =
  | "ONE_HAND"
  | "ONE_OR_TWO_HANDS"
  | "TWO_HANDS";

export type EquipmentSlot =
  | "HEAD"
  | "TORSO"
  | "LEGS"
  | "FEET"
  | "HANDS"
  | "MAIN_HAND"
  | "OFF_HAND"
  | "BOTH_HANDS"
  | "BACK"
  | "WAIST"
  | "ACCESSORY";

export type ItemAccessibility = "IMMEDIATE" | "QUICK" | "WORN" | "STOWED";

export type EncumbranceTier =
  | "NORMAL"
  | "LIGHTLY_ENCUMBERED"
  | "HEAVILY_ENCUMBERED"
  | "OVERLOADED";

export interface Inventory {
  items: InventoryItem[];
  total_weight: number;
  carrying_capacity: number;
  load_ratio: number;
  encumbrance: EncumbranceTier;
}

export interface QuestObjective {
  id: string;
  description: string;
  completed: boolean;
}

export interface Quest {
  quest_id: string;
  name: string;
  description: string;
  status: string;
  objectives: QuestObjective[];
}

export interface MapRegion {
  id: string;
  name: string | null;
  description: string | null;
  discovery_status: string;
}

export interface MapLocation {
  id: string;
  region_id: string;
  name: string | null;
  type: string;
  x: number | null;
  y: number | null;
  discovery_status: string;
}

export interface MapConnection {
  from_location_id: string;
  to_location_id: string;
  direction: string | null;
  connection_type: string;
  distance: number;
  danger: number;
  travel_time_modifier: number;
}

export interface MapData {
  regions: MapRegion[];
  locations: MapLocation[];
  connections: MapConnection[];
}

// Phase 20A/20B/20C/20F — the character-specific Map View projection
// (app.game.map.view.MapViewData). Deliberately a different, smaller
// shape than MapData above: precision is always present (never a raw
// discovery-status inference the frontend has to redo).
export interface MapViewRegion {
  id: string;
  name: string | null;
  discovery_status: string;
}

export interface MapViewLocation {
  id: string;
  region_id: string;
  subregion_id: string | null;
  parent_location_id: string | null;
  type: string;
  name: string | null;
  precision: string | null;
  x: number | null;
  y: number | null;
  discovery_status: string;
  source: string;
  stale: boolean;
  known_aspects: string[];
}

export interface MapViewRoute {
  from_location_id: string;
  to_location_id: string;
  direction: string | null;
  connection_type: string;
  distance: number;
  danger: number;
  travel_time_modifier: number;
}

// Phase 20M — a planned path over the character's OWN known routes
// only; `known: false` is a legitimate answer ("no known route"), not
// an error, and never falls back to computing over unknown geography.
export interface RoutePlanSegment {
  from_location_id: string;
  to_location_id: string;
  direction: string | null;
  connection_type: string;
  distance: number;
  danger: number;
}

export interface RoutePlan {
  known: boolean;
  from_location_id: string;
  to_location_id: string;
  segments: RoutePlanSegment[];
  total_distance: number;
  estimated_minutes: number;
  max_danger: number;
}

// Phase 20J — a player-owned note pinned to a known location. Never
// world truth: purely user-authored text the System organizes but
// never acts on.
export interface MapViewAnnotation {
  id: string;
  location_id: string;
  text: string;
  created_at: string;
}

export interface MapViewData {
  campaign_id: string;
  character_id: string;
  scope: string | null;
  regions: MapViewRegion[];
  locations: MapViewLocation[];
  routes: MapViewRoute[];
  annotations: MapViewAnnotation[];
  position_location_id: string | null;
  position_precision: string | null;
}

export interface JournalEvent {
  id: string;
  event_type: string;
  actor_type: string;
  actor_id: string;
  world_minute: number;
  importance: number;
  created_at: string;
}

export interface JournalMemory {
  id: string;
  subject: string;
  summary_text: string;
  importance: number;
  source_event_id: string | null;
  created_at: string;
}

export interface Journal {
  events: JournalEvent[];
  memories: JournalMemory[];
}
