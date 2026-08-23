import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { EntityVisual } from "@/components/EntityVisual";
import type { VisualAsset, VisualGenerationRequest } from "@/types/game";

const mocks = vi.hoisted(() => ({
  getCurrentVisualAsset: vi.fn(),
  generateVisualAsset: vi.fn(),
  getVisualGenerationRequest: vi.fn(),
  retryVisualGenerationRequest: vi.fn(),
}));

vi.mock("@/api/visual", () => ({
  getCurrentVisualAsset: mocks.getCurrentVisualAsset,
  generateVisualAsset: mocks.generateVisualAsset,
  getVisualGenerationRequest: mocks.getVisualGenerationRequest,
  retryVisualGenerationRequest: mocks.retryVisualGenerationRequest,
}));

function asset(overrides: Partial<VisualAsset> = {}): VisualAsset {
  return {
    id: "vasset_1",
    entity_type: "npc",
    entity_id: "npc_1",
    asset_type: "NPC_PORTRAIT",
    mime_type: "image/png",
    width: 1024,
    height: 1024,
    validation_status: "UNREVIEWED",
    is_current: true,
    is_canonical_reference: false,
    url: "/api/campaigns/campaign_1/visual-assets/vasset_1/file",
    ...overrides,
  };
}

function request(overrides: Partial<VisualGenerationRequest> = {}): VisualGenerationRequest {
  return {
    id: "vgen_1",
    status: "PENDING",
    entity_type: "npc",
    entity_id: "npc_1",
    asset_type: "NPC_PORTRAIT",
    workflow_key: "EVERREACH_NPC_PORTRAIT",
    workflow_version: "V1",
    attempt_count: 1,
    error_code: null,
    error_message: null,
    result_asset_id: null,
    ...overrides,
  };
}

function renderEntityVisual() {
  return render(
    <EntityVisual
      campaignId="campaign_1"
      entityType="npc"
      entityId="npc_1"
      assetType="NPC_PORTRAIT"
      placeholderGlyph="☺"
      label="Retrato de Serel"
      generateLabel="Gerar retrato"
      regenerateLabel="Regenerar retrato"
    />,
  );
}

describe("EntityVisual", () => {
  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getCurrentVisualAsset.mockRejectedValue(new ApiError(404, "not found"));
  });

  it("busca e exibe o asset visual atual quando ele existe", async () => {
    mocks.getCurrentVisualAsset.mockResolvedValue(asset());

    renderEntityVisual();

    await waitFor(() =>
      expect(screen.getByRole("img", { name: "Retrato de Serel" })).toHaveAttribute(
        "src",
        "/api/campaigns/campaign_1/visual-assets/vasset_1/file",
      ),
    );
  });

  it("mostra o placeholder quando não existe asset ainda", async () => {
    renderEntityVisual();

    await waitFor(() => expect(mocks.getCurrentVisualAsset).toHaveBeenCalled());
    expect(document.querySelector(".asset-slot-placeholder")).toBeInTheDocument();
  });

  it("nunca dispara geração automaticamente ao montar, mesmo sem asset", async () => {
    renderEntityVisual();

    await waitFor(() => expect(mocks.getCurrentVisualAsset).toHaveBeenCalled());
    expect(mocks.generateVisualAsset).not.toHaveBeenCalled();
  });

  it("a ação explícita de gerar envia a requisição esperada ao backend", async () => {
    mocks.generateVisualAsset.mockResolvedValue(request());

    renderEntityVisual();
    await waitFor(() => expect(mocks.getCurrentVisualAsset).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /Abrir detalhes/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Gerar retrato" }));

    await waitFor(() =>
      expect(mocks.generateVisualAsset).toHaveBeenCalledWith("campaign_1", "npc", "npc_1", "NPC_PORTRAIT"),
    );
  });

  it("faz polling do status até a geração terminar, com limpeza no unmount", async () => {
    mocks.generateVisualAsset.mockResolvedValue(request({ status: "PENDING" }));
    mocks.getVisualGenerationRequest
      .mockResolvedValueOnce(request({ status: "IN_PROGRESS" }))
      .mockResolvedValueOnce(request({ status: "COMPLETED", result_asset_id: "vasset_2" }));
    mocks.getCurrentVisualAsset
      .mockRejectedValueOnce(new ApiError(404, "not found")) // initial mount
      .mockResolvedValueOnce(asset({ id: "vasset_2", url: "/api/campaigns/campaign_1/visual-assets/vasset_2/file" }));

    // Real timers for mount + expanding the panel; fake timers are
    // installed BEFORE the click that starts polling, so the
    // setTimeout pollRequest schedules is one advanceTimersByTimeAsync
    // actually controls (a setTimeout created under real timers would
    // fire on its own real-time schedule regardless of fake advances).
    const { unmount } = renderEntityVisual();
    await waitFor(() => expect(mocks.getCurrentVisualAsset).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /Abrir detalhes/ }));

    vi.useFakeTimers();
    try {
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Gerar retrato" }));
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(screen.getByText("Criando imagem…")).toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(mocks.getVisualGenerationRequest).toHaveBeenCalledTimes(1);
      expect(screen.getByText("Criando imagem…")).toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(mocks.getVisualGenerationRequest).toHaveBeenCalledTimes(2);
      expect(mocks.getCurrentVisualAsset).toHaveBeenCalledTimes(2);
      expect(
        screen.getByRole("img", { name: "Retrato de Serel" }).getAttribute("src"),
      ).toBe("/api/campaigns/campaign_1/visual-assets/vasset_2/file");

      // COMPLETED — no further polling should ever be scheduled.
      const callsAfterCompletion = mocks.getVisualGenerationRequest.mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      expect(mocks.getVisualGenerationRequest).toHaveBeenCalledTimes(callsAfterCompletion);
    } finally {
      vi.useRealTimers();
      unmount();
    }
  });

  it("para de fazer polling ao desmontar, sem chamadas órfãs", async () => {
    mocks.generateVisualAsset.mockResolvedValue(request({ status: "IN_PROGRESS" }));
    mocks.getVisualGenerationRequest.mockResolvedValue(request({ status: "IN_PROGRESS" }));

    const { unmount } = renderEntityVisual();
    await waitFor(() => expect(mocks.getCurrentVisualAsset).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /Abrir detalhes/ }));

    vi.useFakeTimers();
    try {
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Gerar retrato" }));
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(screen.getByText("Criando imagem…")).toBeInTheDocument();

      unmount();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30000);
      });
      expect(mocks.getVisualGenerationRequest).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("mantém a UI utilizável quando a geração falha", async () => {
    mocks.generateVisualAsset.mockResolvedValue(request({ status: "FAILED", error_code: "COMFYUI_OFFLINE" }));

    renderEntityVisual();
    await waitFor(() => expect(mocks.getCurrentVisualAsset).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /Abrir detalhes/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Gerar retrato" }));

    expect(await screen.findByText("A geração falhou.")).toBeInTheDocument();
    // No raw backend error code/message ever surfaces to the player.
    expect(screen.queryByText(/COMFYUI_OFFLINE/)).not.toBeInTheDocument();
    // The retry affordance replaces the generate one; UI stays interactive.
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("ignora cliques duplicados em Gerar enquanto uma requisição está pendente", async () => {
    let resolveGenerate: (value: VisualGenerationRequest) => void = () => {};
    mocks.generateVisualAsset.mockReturnValue(
      new Promise<VisualGenerationRequest>((resolve) => {
        resolveGenerate = resolve;
      }),
    );
    mocks.getVisualGenerationRequest.mockResolvedValue(request({ status: "IN_PROGRESS" }));

    renderEntityVisual();
    await waitFor(() => expect(mocks.getCurrentVisualAsset).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /Abrir detalhes/ }));
    const generateButton = await screen.findByRole("button", { name: "Gerar retrato" });
    fireEvent.click(generateButton);

    await act(async () => {
      resolveGenerate(request({ status: "IN_PROGRESS" }));
      await Promise.resolve();
    });

    // While generating, the button is replaced by a status line — a
    // second physical click on "Gerar retrato" is structurally impossible.
    expect(screen.queryByRole("button", { name: "Gerar retrato" })).not.toBeInTheDocument();
    expect(mocks.generateVisualAsset).toHaveBeenCalledTimes(1);
  });

  it("usa a URL do backend diretamente, sem construir caminhos locais", async () => {
    mocks.getCurrentVisualAsset.mockResolvedValue(
      asset({ url: "/api/campaigns/campaign_1/visual-assets/vasset_1/file" }),
    );

    renderEntityVisual();

    await waitFor(() => {
      const src = screen.getByRole("img", { name: "Retrato de Serel" }).getAttribute("src") ?? "";
      expect(src).toBe("/api/campaigns/campaign_1/visual-assets/vasset_1/file");
    });
    const src = screen.getByRole("img", { name: "Retrato de Serel" }).getAttribute("src") ?? "";
    expect(src).not.toContain("E:\\");
    expect(src).not.toContain("127.0.0.1:8188");
    expect(src).not.toContain("file://");
  });
});
