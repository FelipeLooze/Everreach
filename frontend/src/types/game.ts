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
  level: number;
  xp: number;
  hp_current: number;
  hp_max: number;
  mana_current: number;
  mana_max: number;
  stamina_current: number;
  stamina_max: number;
  status: "ALIVE" | "DEAD";
  region_id: string | null;
  location_id: string | null;
}

export interface RegionSummary {
  id: string;
  name: string;
  description: string;
  main_boss_name: string;
  main_boss_location: string;
}

export interface LocationSummary {
  id: string;
  name: string;
  type: string;
  description: string;
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
}

export interface NearbySimulatedPlayer {
  id: string;
  name: string;
  level: number;
  archetype: string;
}

export interface ActiveQuestSummary {
  quest_id: string;
  name: string;
  status: string;
}

export interface GameState {
  character: Character;
  region: RegionSummary | null;
  location: LocationSummary | null;
  world_time: WorldTime | null;
  nearby_npcs: NearbyNPC[];
  nearby_simulated_players: NearbySimulatedPlayer[];
  active_quests: ActiveQuestSummary[];
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
  name: string;
  value: number;
}

export interface CharacterSkill {
  name: string;
  mastery: number;
}

export interface CharacterTechnique {
  name: string;
  description: string;
}

export interface CharacterSheet {
  character: Character;
  attributes: CharacterAttribute[];
  skills: CharacterSkill[];
  techniques: CharacterTechnique[];
}

export interface InventoryItem {
  item_id: string;
  name: string;
  type: string;
  quantity: number;
  equipped: boolean;
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
  name: string;
  description: string;
  discovery_status: string;
  main_boss_name: string;
  main_boss_location: string;
  main_boss_requirements: string;
}

export interface MapLocation {
  id: string;
  region_id: string;
  name: string;
  type: string;
  x: number;
  y: number;
  discovery_status: string;
}

export interface MapConnection {
  from_location_id: string;
  to_location_id: string;
  connection_type: string;
  distance: number;
  danger: number;
}

export interface MapData {
  regions: MapRegion[];
  locations: MapLocation[];
  connections: MapConnection[];
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
