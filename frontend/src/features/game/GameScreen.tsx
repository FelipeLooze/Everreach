import { useEffect, useState } from "react";
import { postAction } from "@/api/actions";
import { getCharacterSheet } from "@/api/character";
import { startWorld } from "@/api/campaigns";
import { getStoryLog } from "@/api/story";
import { Panel } from "@/components/Panel";
import { StatusBar } from "@/components/StatusBar";
import { CharacterSheetPanel } from "@/features/character/CharacterSheetPanel";
import { ActionInput } from "@/features/game/ActionInput";
import { NarrativeLog, type NarrativeEntry } from "@/features/game/NarrativeLog";
import { StoryLogPanel } from "@/features/game/StoryLogPanel";
import { InventoryPanel } from "@/features/inventory/InventoryPanel";
import { JournalPanel } from "@/features/journal/JournalPanel";
import { MapPanel } from "@/features/map/MapPanel";
import { QuestPanel } from "@/features/quests/QuestPanel";
import { SettingsPanel } from "@/features/settings/SettingsPanel";
import { useGameState } from "@/hooks/useGameState";
import { useGameStore } from "@/stores/useGameStore";
import type { CharacterTechnique, StoryEntry } from "@/types/game";

type PanelKind = "map" | "inventory" | "character" | "quests" | "journal" | "log" | "settings" | null;

let entryCounter = 0;
const nextId = () => `entry_${entryCounter++}`;

function latestExchange(entries: StoryEntry[]): NarrativeEntry[] {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    if (entries[index].kind === "player") return entries.slice(index);
  }
  return entries.slice(-1);
}

export function GameScreen() {
  const { campaignId, characterId, setState, clearSession } = useGameStore();
  const { state, loading, error } = useGameState();
  const [entries, setEntries] = useState<NarrativeEntry[]>([]);
  const [storyEntries, setStoryEntries] = useState<StoryEntry[]>([]);
  const [storyError, setStoryError] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<PanelKind>(null);
  const [submitting, setSubmitting] = useState(false);
  const [startingWorld, setStartingWorld] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [techniques, setTechniques] = useState<CharacterTechnique[]>([]);

  useEffect(() => {
    if (!state || !campaignId || !characterId) return;
    setStoryError(null);
    getStoryLog(campaignId, characterId)
      .then((story) => {
        setStoryEntries(story.entries);
        setEntries(latestExchange(story.entries));
      })
      .catch((err) => setStoryError(err instanceof Error ? err.message : "Falha ao carregar o log."));
  }, [campaignId, characterId, state?.opening_narrative]);

  useEffect(() => {
    if (!campaignId || !characterId) return;
    getCharacterSheet(campaignId, characterId)
      .then((sheet) => setTechniques(sheet.techniques))
      .catch(() => setTechniques([]));
  }, [campaignId, characterId]);

  if (!campaignId || !characterId) {
    return <p>Nenhuma campanha ativa. Comece uma nova primeiro.</p>;
  }

  const handleAction = async (text: string, techniqueId?: string) => {
    setEntries((prev) => [...prev, { id: nextId(), kind: "player", text }]);
    setSubmitting(true);
    setActionError(null);
    try {
      const result = await postAction(campaignId, characterId, text, techniqueId);
      setState(result.state);
      const persistedEntries: StoryEntry[] = [
        { id: nextId(), kind: "player", text, created_at: new Date().toISOString() },
        { id: nextId(), kind: "narrator", text: result.narrative, created_at: new Date().toISOString() },
      ];
      setStoryEntries((prev) => [...prev, ...persistedEntries]);
      setEntries((prev) => [
        ...prev,
        {
          id: nextId(),
          kind: "narrator",
          text: result.narrator_unavailable
            ? `${result.narrative}\n[IA narradora indisponível — mostrando apenas o resultado mecânico]`
            : result.narrative,
        },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Falha na ação.";
      setActionError(message);
      setEntries((prev) => [...prev, { id: nextId(), kind: "system", text: `[Erro: ${message}]` }]);
    } finally {
      setSubmitting(false);
    }
  };

  const handleStartWorld = async () => {
    setStartingWorld(true);
    setActionError(null);
    try {
      const result = await startWorld(campaignId, characterId);
      setState(result.state);
      const openingText = result.narrator_unavailable
        ? `${result.narrative}\n[IA narradora indisponível — mostrando a introdução de reserva]`
        : result.narrative;
      const openingEntry: StoryEntry = {
        id: nextId(),
        kind: "narrator",
        text: openingText,
        created_at: new Date().toISOString(),
      };
      setStoryEntries([openingEntry]);
      setEntries([openingEntry]);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Não foi possível iniciar o mundo.");
    } finally {
      setStartingWorld(false);
    }
  };

  const worldStarted = Boolean(state?.region && state.location);

  return (
    <div className="game-screen">
      {state && <StatusBar state={state} />}
      {loading && !state && <p>Carregando o mundo…</p>}
      {error && <p className="panel-error">{error}</p>}

      <NarrativeLog entries={entries} />

      {actionError && <p className="panel-error">{actionError}</p>}
      {state && !worldStarted && (
        <div className="world-start">
          <p>Seu personagem está pronto. Inicie o mundo para começar sua jornada.</p>
          <button onClick={handleStartWorld} disabled={startingWorld}>
            {startingWorld ? "Iniciando mundo…" : "Iniciar mundo"}
          </button>
        </div>
      )}
      {worldStarted && (
        <ActionInput
          onSubmit={handleAction}
          disabled={submitting || state?.character.status !== "ALIVE"}
          techniques={techniques}
        />
      )}

      <div className="action-bar">
        <button onClick={() => setActivePanel("map")}>Mapa</button>
        <button onClick={() => setActivePanel("inventory")}>Inventário</button>
        <button onClick={() => setActivePanel("character")}>Personagem</button>
        <button onClick={() => setActivePanel("quests")}>Missão</button>
        <button onClick={() => setActivePanel("journal")}>Diário</button>
        <button onClick={() => setActivePanel("log")}>Log</button>
        <button onClick={() => setActivePanel("settings")}>Configurações</button>
      </div>

      {activePanel === "map" && (
        <Panel title="Mapa" onClose={() => setActivePanel(null)}>
          <MapPanel campaignId={campaignId} characterId={characterId} />
        </Panel>
      )}
      {activePanel === "inventory" && (
        <Panel title="Inventário" onClose={() => setActivePanel(null)}>
          <InventoryPanel campaignId={campaignId} characterId={characterId} />
        </Panel>
      )}
      {activePanel === "character" && (
        <Panel title="Personagem" onClose={() => setActivePanel(null)}>
          <CharacterSheetPanel campaignId={campaignId} characterId={characterId} />
        </Panel>
      )}
      {activePanel === "quests" && (
        <Panel title="Missão" onClose={() => setActivePanel(null)}>
          <QuestPanel campaignId={campaignId} characterId={characterId} />
        </Panel>
      )}
      {activePanel === "journal" && (
        <Panel title="Diário" onClose={() => setActivePanel(null)}>
          <JournalPanel campaignId={campaignId} characterId={characterId} />
        </Panel>
      )}
      {activePanel === "log" && (
        <Panel title="Log da história" onClose={() => setActivePanel(null)}>
          <StoryLogPanel entries={storyEntries} error={storyError} />
        </Panel>
      )}
      {activePanel === "settings" && (
        <Panel title="Configurações" onClose={() => setActivePanel(null)}>
          <SettingsPanel onExit={clearSession} />
        </Panel>
      )}
    </div>
  );
}
