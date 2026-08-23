/**
 * Phase 23D-O — Frontend Visual Asset Consumption.
 *
 * The one reusable bridge between a game entity (an NPC, an item
 * instance, ...) and the real backend visual-asset pipeline
 * (src/api/visual.ts). Mounting this component only ever performs a
 * cheap GET of the entity's CURRENT asset — never a generation.
 * Generation only ever happens from the explicit "Gerar"/"Regenerar"
 * action inside the expanded panel, which a player must deliberately
 * open and click; nothing here triggers ComfyUI work on its own.
 *
 * The frontend never learns which workflow the backend chose, whether
 * a canonical reference exists, or anything about ComfyUI — it only
 * ever sends {entity_type, entity_id, asset_type} and reads back a
 * VisualAsset/VisualGenerationRequest, exactly like every other
 * concept this app already understands.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  generateVisualAsset,
  getCurrentVisualAsset,
  getVisualGenerationRequest,
  retryVisualGenerationRequest,
} from "@/api/visual";
import { AssetSlot } from "@/components/AssetSlot";
import type { VisualAsset, VisualGenerationRequest } from "@/types/game";

// ComfyUI cold-loading a model from disk has legitimately taken close
// to two minutes on the reference machine — polling must stay generous
// enough to never give up on a real, still-in-progress generation.
const POLL_INTERVAL_MS = 3000;
const MAX_POLL_MS = 6 * 60 * 1000;

interface EntityVisualProps {
  campaignId: string;
  entityType: string;
  entityId: string;
  assetType: string;
  placeholderGlyph: string;
  label: string;
  generateLabel: string;
  regenerateLabel: string;
}

export function EntityVisual({
  campaignId,
  entityType,
  entityId,
  assetType,
  placeholderGlyph,
  label,
  generateLabel,
  regenerateLabel,
}: EntityVisualProps) {
  const [asset, setAsset] = useState<VisualAsset | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [request, setRequest] = useState<VisualGenerationRequest | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const mountedRef = useRef(true);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollDeadlineRef = useRef(0);

  const clearPoll = useCallback(() => {
    if (pollTimeoutRef.current !== null) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
  }, []);

  const refreshCurrentAsset = useCallback(async () => {
    try {
      const current = await getCurrentVisualAsset(campaignId, entityType, entityId, assetType);
      if (mountedRef.current) setAsset(current);
    } catch {
      // A 404 here means "no current asset yet" — a normal state, not
      // an error to surface.
      if (mountedRef.current) setAsset(null);
    }
  }, [campaignId, entityType, entityId, assetType]);

  // Entity identity changed (or first mount): reset everything and do
  // exactly one cheap read. Never a generation.
  useEffect(() => {
    mountedRef.current = true;
    setAsset(null);
    setRequest(null);
    setActionError(null);
    setExpanded(false);
    clearPoll();
    refreshCurrentAsset();

    return () => {
      mountedRef.current = false;
      clearPoll();
    };
  }, [campaignId, entityType, entityId, assetType, clearPoll, refreshCurrentAsset]);

  const pollRequest = useCallback(
    (requestId: string) => {
      if (Date.now() > pollDeadlineRef.current) {
        clearPoll();
        return;
      }
      pollTimeoutRef.current = setTimeout(async () => {
        if (!mountedRef.current) return;
        try {
          const updated = await getVisualGenerationRequest(campaignId, requestId);
          if (!mountedRef.current) return;
          setRequest(updated);
          if (updated.status === "COMPLETED") {
            clearPoll();
            await refreshCurrentAsset();
          } else if (updated.status === "FAILED") {
            clearPoll();
          } else {
            pollRequest(requestId);
          }
        } catch {
          // A transient status-read failure should not abandon an
          // otherwise-valid, still-running backend request.
          if (mountedRef.current) pollRequest(requestId);
        }
      }, POLL_INTERVAL_MS);
    },
    [campaignId, clearPoll, refreshCurrentAsset],
  );

  const beginPolling = (createdOrRetried: VisualGenerationRequest) => {
    setRequest(createdOrRetried);
    if (createdOrRetried.status === "COMPLETED") {
      refreshCurrentAsset();
    } else if (createdOrRetried.status === "PENDING" || createdOrRetried.status === "IN_PROGRESS") {
      pollDeadlineRef.current = Date.now() + MAX_POLL_MS;
      pollRequest(createdOrRetried.id);
    }
    // A FAILED result from the initial call is just displayed as-is —
    // no polling needed for a request that is already finished.
  };

  const startGeneration = async () => {
    if (request && (request.status === "PENDING" || request.status === "IN_PROGRESS")) return;
    setActionError(null);
    try {
      const created = await generateVisualAsset(campaignId, entityType, entityId, assetType);
      beginPolling(created);
    } catch {
      setActionError("Não foi possível iniciar a geração agora.");
    }
  };

  const retryGeneration = async () => {
    if (!request) return;
    setActionError(null);
    try {
      const retried = await retryVisualGenerationRequest(campaignId, request.id);
      beginPolling(retried);
    } catch {
      setActionError("Não foi possível tentar novamente agora.");
    }
  };

  const generating = request?.status === "PENDING" || request?.status === "IN_PROGRESS";
  const failed = request?.status === "FAILED";

  return (
    <div className="entity-visual">
      <button
        type="button"
        className="entity-visual-trigger"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-label={expanded ? `Fechar detalhes de ${label}` : `Abrir detalhes de ${label}`}
      >
        <AssetSlot assetUrl={asset?.url} placeholderGlyph={placeholderGlyph} label={label} />
      </button>

      {expanded && (
        <div className="entity-visual-panel">
          {generating && <p className="entity-visual-status">Criando imagem…</p>}
          {failed && <p className="entity-visual-status entity-visual-status-error">A geração falhou.</p>}
          {actionError && <p className="entity-visual-status entity-visual-status-error">{actionError}</p>}

          {!generating && failed && (
            <button type="button" className="entity-visual-action" onClick={retryGeneration}>
              Tentar novamente
            </button>
          )}
          {!generating && !failed && (
            <button type="button" className="entity-visual-action" onClick={startGeneration}>
              {asset ? regenerateLabel : generateLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
