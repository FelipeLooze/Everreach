import { useEffect, useState } from "react";
import { getActionUndoStatus, postAction, undoLastAction } from "@/api/actions";
import { getCharacterSheet } from "@/api/character";
import { startWorld } from "@/api/campaigns";
import { getStoryLog, regenerateLastNarrative } from "@/api/story";
import { Panel } from "@/components/Panel";
import { StatusBar } from "@/components/StatusBar";
import { CharacterSheetPanel } from "@/features/character/CharacterSheetPanel";
import { CombatPanel } from "@/features/combat/CombatPanel";
import { ActionInput } from "@/features/game/ActionInput";
import { GameSidebar } from "@/features/game/GameSidebar";
import { NarrativeLog, type NarrativeEntry } from "@/features/game/NarrativeLog";
import { RegenerateNarrative } from "@/features/game/RegenerateNarrative";
import { StoryLogPanel } from "@/features/game/StoryLogPanel";
import { UndoLastAction } from "@/features/game/UndoLastAction";
import { InventoryPanel } from "@/features/inventory/InventoryPanel";
import { JournalPanel } from "@/features/journal/JournalPanel";
import { MapPanel } from "@/features/map/MapPanel";
import { QuestPanel } from "@/features/quests/QuestPanel";
import { SettingsPanel } from "@/features/settings/SettingsPanel";
import { SocialPanel } from "@/features/social/SocialPanel";
import { useGameState } from "@/hooks/useGameState";
import { useGameStore } from "@/stores/useGameStore";
import type { ActionUndoStatus, CharacterTechnique, StoryEntry } from "@/types/game";

type PanelKind = "map" | "inventory" | "character" | "quests" | "social" | "journal" | "log" | "settings" | "combat" | null;

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
  const [regenerating, setRegenerating] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [undoStatus, setUndoStatus] = useState<ActionUndoStatus>({
    available: false,
    action_text: null,
    mechanical_summary: null,
  });
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

  useEffect(() => {
    if (!campaignId || !characterId) return;
    getActionUndoStatus(campaignId, characterId)
      .then(setUndoStatus)
      .catch(() => setUndoStatus({ available: false, action_text: null, mechanical_summary: null }));
  }, [campaignId, characterId, state?.opening_narrative]);

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
      setUndoStatus({
        available: true,
        action_text: text,
        mechanical_summary: result.mechanical_summary,
      });
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

  const handleRegenerate = async (feedback: string) => {
    setRegenerating(true);
    setActionError(null);
    try {
      await regenerateLastNarrative(campaignId, characterId, feedback);
      const story = await getStoryLog(campaignId, characterId);
      setStoryEntries(story.entries);
      setEntries(latestExchange(story.entries));
      return true;
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Não foi possível regenerar a mensagem.");
      return false;
    } finally {
      setRegenerating(false);
    }
  };

  const handleUndo = async (reason: string) => {
    setUndoing(true);
    setActionError(null);
    try {
      const result = await undoLastAction(campaignId, characterId, reason);
      setState(result.state);
      const story = await getStoryLog(campaignId, characterId);
      setStoryEntries(story.entries);
      setEntries([
        ...latestExchange(story.entries),
        { id: nextId(), kind: "system", text: "[A última ação foi desfeita.]" },
      ]);
      setUndoStatus({ available: false, action_text: null, mechanical_summary: null });
      return true;
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Não foi possível desfazer a ação.");
      return false;
    } finally {
      setUndoing(false);
    }
  };

  const worldStarted = Boolean(state?.region && state.location);

  return (
    <div className="game-screen">
      {state && <StatusBar state={state} />}
      <main className="game-content">
        <section className="game-main">
          {loading && !state && <p className="game-feedback">Carregando o mundo…</p>}
          {error && <p className="panel-error game-feedback">{error}</p>}
          <NarrativeLog entries={entries} pending={submitting || startingWorld || regenerating || undoing} />
          {actionError && <p className="panel-error action-error">{actionError}</p>}
          {state && !worldStarted && (
            <div className="world-start">
              <p>Seu personagem está pronto. Inicie o mundo para começar sua jornada.</p>
              <button onClick={handleStartWorld} disabled={startingWorld}>
                {startingWorld ? "Iniciando mundo…" : "Iniciar mundo"}
              </button>
            </div>
          )}
          {worldStarted && (
            <>
              {entries.some((entry) => entry.kind === "narrator") && (
                <div className="narrative-revision-actions">
                  <RegenerateNarrative
                    onRegenerate={handleRegenerate}
                    disabled={submitting || regenerating || undoing}
                  />
                  {undoStatus.available && undoStatus.action_text && (
                    <UndoLastAction
                      actionText={undoStatus.action_text}
                      onUndo={handleUndo}
                      disabled={submitting || regenerating || undoing}
                    />
                  )}
                </div>
              )}
              <ActionInput
                onSubmit={handleAction}
                disabled={submitting || regenerating || undoing || state?.character.status !== "ALIVE"}
                techniques={techniques}
              />
            </>
          )}
        </section>
        {state && <GameSidebar state={state} campaignId={campaignId} />}
      </main>

      <nav className="action-bar" aria-label="Menu do jogo">
        <button onClick={() => setActivePanel("character")}><span>PERSONAGEM</span></button>
        <button onClick={() => setActivePanel("inventory")}><span>INVENTÁRIO</span></button>
        <button onClick={() => setActivePanel("character")}><span>SKILLS</span></button>
        <button onClick={() => setActivePanel("map")}><span>MAPA</span></button>
        <button onClick={() => setActivePanel("quests")}><span>QUESTS</span></button>
        <button onClick={() => setActivePanel("social")}><span>SOCIAL</span></button>
        <button onClick={() => setActivePanel("journal")}><span>DIÁRIO</span></button>
        <button onClick={() => setActivePanel("log")}><span>HISTÓRIA</span></button>
        <button onClick={() => setActivePanel("settings")}><span>SISTEMA</span></button>
        {state?.active_encounter && (
          <button className="action-bar-alert" onClick={() => setActivePanel("combat")}>
            <span>COMBATE</span>
          </button>
        )}
      </nav>

      {activePanel === "map" && (
        <Panel title="Mapa" onClose={() => setActivePanel(null)}>
          <MapPanel campaignId={campaignId} characterId={characterId} />
        </Panel>
      )}
      {activePanel === "inventory" && (
        <Panel title="Inventário" size="wide" onClose={() => setActivePanel(null)}>
          <InventoryPanel campaignId={campaignId} characterId={characterId} />
        </Panel>
      )}
      {activePanel === "character" && (
        <Panel title="Personagem" size="wide" onClose={() => setActivePanel(null)}>
          <CharacterSheetPanel campaignId={campaignId} characterId={characterId} />
        </Panel>
      )}
      {activePanel === "quests" && (
        <Panel title="Missão" onClose={() => setActivePanel(null)}>
          <QuestPanel campaignId={campaignId} characterId={characterId} />
        </Panel>
      )}
      {activePanel === "social" && (
        <Panel title="Grupos e organizações" size="wide" onClose={() => setActivePanel(null)}>
          <SocialPanel campaignId={campaignId} characterId={characterId} />
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
      {activePanel === "combat" && (
        <Panel title="Combate" onClose={() => setActivePanel(null)}>
          <CombatPanel encounter={state?.active_encounter ?? null} />
        </Panel>
      )}
    </div>
  );
}
