const LOCATION_TYPE_LABELS: Record<string, string> = {
  village: "vila",
  forest: "floresta",
  road: "estrada",
  river: "rio",
  clearing: "clareira",
  generic: "local",
};

const CHARACTER_ATTRIBUTE_LABELS: Record<string, string> = {
  Strength: "Força",
  Agility: "Agilidade",
  Vitality: "Vitalidade",
  Intelligence: "Inteligência",
  Wisdom: "Sabedoria",
  Endurance: "Resistência",
};

const DISCOVERY_STATUS_LABELS: Record<string, string> = {
  UNKNOWN: "desconhecido",
  RUMORED: "rumor",
  DISCOVERED: "descoberto",
  VISITED: "visitado",
  MAPPED: "mapeado",
};

const QUEST_STATUS_LABELS: Record<string, string> = {
  NOT_STARTED: "não iniciada",
  ACTIVE: "ativa",
  COMPLETED: "concluída",
  FAILED: "fracassada",
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  CAMPAIGN_CREATED: "Campanha criada",
  WORLD_STARTED: "Mundo iniciado",
  STORY_EXCHANGE: "Troca narrativa",
  CHARACTER_CREATED: "Personagem criado",
  PLAYER_MOVED: "Você se moveu",
  PLAYER_MET_NPC: "Você conheceu alguém",
  PLAYER_TALKED_TO_NPC: "Você conversou com alguém",
  PLAYER_GAINED_ITEM: "Você ganhou um item",
  PLAYER_LOST_ITEM: "Você perdeu um item",
  PLAYER_RESTED: "Você descansou",
  PLAYER_GAINED_XP: "Você ganhou experiência",
  PLAYER_LEVELED_UP: "Você subiu de nível",
  PLAYER_DIED: "Você morreu",
  ACTION_CHECK_RESULT: "Resultado de uma checagem",
  QUEST_STARTED: "Missão iniciada",
  QUEST_OBJECTIVE_COMPLETED: "Objetivo de missão concluído",
  QUEST_COMPLETED: "Missão concluída",
  NPC_DIED: "Um NPC morreu",
  REGION_DISCOVERED: "Região descoberta",
  LOCATION_DISCOVERED: "Local descoberto",
  BOSS_DISCOVERED: "Chefe descoberto",
  BOSS_DEFEATED: "Chefe derrotado",
  NEW_TECHNIQUE_CREATED: "Nova técnica criada",
  WORLD_TIME_ADVANCED: "O tempo avançou",
  SIMULATED_PLAYER_MOVED: "Um viajante se moveu",
  SIMULATED_PLAYER_TRAINED: "Um viajante treinou",
  RELATIONSHIP_CHANGED: "Uma relação mudou",
  KNOWLEDGE_PROPAGATED: "Um conhecimento foi compartilhado",
};

function translate(map: Record<string, string>, key: string): string {
  return map[key] ?? key;
}

export const locationTypeLabel = (type: string) => translate(LOCATION_TYPE_LABELS, type);
export const characterAttributeLabel = (name: string) => translate(CHARACTER_ATTRIBUTE_LABELS, name);
export const discoveryStatusLabel = (status: string) => translate(DISCOVERY_STATUS_LABELS, status);
export const questStatusLabel = (status: string) => translate(QUEST_STATUS_LABELS, status);
export const eventTypeLabel = (type: string) => translate(EVENT_TYPE_LABELS, type);
