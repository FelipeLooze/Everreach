const LOCATION_TYPE_LABELS: Record<string, string> = {
  village: "vila",
  forest: "floresta",
  road: "estrada",
  river: "rio",
  clearing: "clareira",
  generic: "local",
};

const CHARACTER_ATTRIBUTE_LABELS: Record<string, string> = {
  STRENGTH: "Força",
  AGILITY: "Agilidade",
  VITALITY: "Vitalidade",
  INTELLIGENCE: "Inteligência",
  WISDOM: "Sabedoria",
  ENDURANCE: "Resistência",
  LUCK: "Sorte",
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

const NPC_ACTIVITY_LABELS: Record<string, string> = {
  RESTING: "descansando",
  WORKING: "trabalhando",
  AVAILABLE: "disponível",
};

const QUEST_STATUS_LABELS: Record<string, string> = {
  NOT_STARTED: "não iniciada",
  ACTIVE: "ativa",
  COMPLETED: "concluída",
  FAILED: "fracassada",
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  CAMPAIGN_CREATED: "Campanha criada",
  WORLD_STARTED: "Primeira Chegada",
  STORY_EXCHANGE: "Troca narrativa",
  CHARACTER_CREATED: "Personagem criado",
  PLAYER_MOVED: "Você se moveu",
  TRAVEL_INCIDENT: "Incidente durante a viagem",
  PLAYER_MET_NPC: "Você conheceu alguém",
  PLAYER_TALKED_TO_NPC: "Você conversou com alguém",
  PLAYER_GAINED_ITEM: "Você ganhou um item",
  PLAYER_LOST_ITEM: "Você perdeu um item",
  PLAYER_RESTED: "Você descansou",
  PLAYER_GAINED_XP: "Você ganhou experiência",
  PLAYER_LEVELED_UP: "Você subiu de nível",
  PLAYER_GAINED_PROFESSION_XP: "Você ganhou experiência profissional",
  PLAYER_PROFESSION_LEVELED_UP: "Sua profissão subiu de nível",
  PLAYER_COMPLETED_PROFESSION_ACTIVITY: "Você praticou uma atividade profissional",
  PLAYER_CLASS_OFFERED: "Uma classe ficou disponível",
  PLAYER_CLASS_OFFER_DELAYED: "Você adiou uma classe",
  PLAYER_CLASS_ACCEPTED: "Você aceitou uma classe",
  PLAYER_ATTRIBUTE_INCREASED: "Um atributo aumentou",
  PLAYER_RESOURCE_MAX_INCREASED: "Um recurso máximo aumentou",
  SIMULATED_PLAYER_GAINED_XP: "Uma pessoa transportada ganhou experiência",
  SIMULATED_PLAYER_LEVELED_UP: "Uma pessoa transportada subiu de nível",
  SIMULATED_PLAYER_GOAL_COMPLETED: "Uma pessoa transportada concluiu um objetivo",
  SIMULATED_PLAYER_GOAL_ASSIGNED: "Uma pessoa transportada assumiu um novo objetivo",
  SIMULATED_PLAYER_DIED: "Uma pessoa transportada morreu",
  SIMULATED_PLAYER_GROUP_CREATED: "Um grupo foi formado",
  SIMULATED_PLAYER_GROUP_JOINED: "Uma pessoa entrou em um grupo",
  SIMULATED_PLAYER_GROUP_LEFT: "Uma pessoa deixou um grupo",
  SIMULATED_PLAYER_GROUP_DISSOLVED: "Um grupo foi dissolvido",
  SIMULATED_PLAYER_GROUP_TRAVEL_STARTED: "Um grupo iniciou uma viagem",
  PLAYER_DIED: "Você morreu",
  ACTION_CHECK_RESULT: "Resultado de uma checagem",
  COMBAT_STARTED: "Combate iniciado",
  COMBAT_PARTICIPANT_JOINED: "Participante entrou no combate",
  COMBAT_PARTICIPANT_LEFT: "Participante deixou o combate",
  COMBAT_INITIATIVE_ROLLED: "Iniciativa definida",
  COMBAT_TURN_ADVANCED: "Turno avançado",
  COMBAT_ACTION_RESOLVED: "Ação de combate resolvida",
  COMBAT_DAMAGE_APPLIED: "Dano de combate aplicado",
  COMBAT_PARTICIPANT_INCAPACITATED: "Participante incapacitado",
  COMBAT_CRITICAL_CHECK_RESOLVED: "Teste de estado crítico resolvido",
  COMBAT_PARTICIPANT_STABILIZED: "Participante estabilizado",
  COMBAT_PARTICIPANT_RECOVERED: "Participante recuperado",
  COMBAT_RESOURCE_SPENT: "Recurso consumido em combate",
  COMBAT_CONDITION_APPLIED: "Condição de combate aplicada",
  COMBAT_CONDITION_TRIGGERED: "Condição de combate ativada",
  COMBAT_CONDITION_EXPIRED: "Condição de combate encerrada",
  COMBAT_CONDITION_REMOVED: "Condição de combate removida",
  COMBAT_TACTICAL_ACTION_RESOLVED: "Ação tática resolvida",
  COMBAT_AUTONOMOUS_DECISION_RESOLVED: "Decisão autônoma de combate",
  COMBAT_ENDED: "Combate encerrado",
  QUEST_STARTED: "Missão iniciada",
  QUEST_OBJECTIVE_COMPLETED: "Objetivo de missão concluído",
  QUEST_COMPLETED: "Missão concluída",
  NPC_DIED: "Um NPC morreu",
  REGION_DISCOVERED: "Região descoberta",
  LOCATION_DISCOVERED: "Local descoberto",
  LOCATION_VISITED: "Local visitado pela primeira vez",
  CONNECTION_DISCOVERED: "Rota descoberta",
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
const CONNECTION_TYPE_LABELS: Record<string, string> = {PATH: "trilha",ROAD: "estrada",};
export const characterAttributeLabel = (key: string) => translate(CHARACTER_ATTRIBUTE_LABELS, key);
export const discoveryStatusLabel = (status: string) => translate(DISCOVERY_STATUS_LABELS, status);
export const npcActivityLabel = (activity: string) => translate(NPC_ACTIVITY_LABELS, activity);
export const questStatusLabel = (status: string) => translate(QUEST_STATUS_LABELS, status);
export const eventTypeLabel = (type: string) => translate(EVENT_TYPE_LABELS, type);
export const connectionTypeLabel = (type: string) => translate(CONNECTION_TYPE_LABELS, type.toUpperCase());
