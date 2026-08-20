import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampaignSetupPage } from "@/pages/CampaignSetupPage";

const mocks = vi.hoisted(() => ({
  listCampaigns: vi.fn(),
  createCampaign: vi.fn(),
  createCharacter: vi.fn(),
  deleteCampaign: vi.fn(),
  setSession: vi.fn(),
}));

vi.mock("@/api/campaigns", () => ({
  listCampaigns: mocks.listCampaigns,
  createCampaign: mocks.createCampaign,
  createCharacter: mocks.createCharacter,
  deleteCampaign: mocks.deleteCampaign,
}));

vi.mock("@/stores/useGameStore", () => ({
  useGameStore: (selector: (state: { setSession: typeof mocks.setSession }) => unknown) =>
    selector({ setSession: mocks.setSession }),
}));

const savedCampaign = {
  id: "campaign_1",
  name: "Vale Persistente",
  created_at: "2026-08-15T12:00:00Z",
  characters: [
    {
      id: "char_1",
      name: "Logan",
      background: null,
      profession_affinity_key: null,
      active_class_id: null,
      level: 0,
      xp: 0,
      hp_current: 20,
      hp_max: 20,
      mana_current: 10,
      mana_max: 10,
      stamina_current: 20,
      stamina_max: 20,
      status: "ALIVE" as const,
      region_id: "region_1",
      location_id: "location_1",
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<CampaignSetupPage />} />
        <Route path="/game" element={<p>Tela do jogo</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CampaignSetupPage", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listCampaigns.mockResolvedValue([savedCampaign]);
    mocks.deleteCampaign.mockResolvedValue({ deleted: true });
    mocks.createCampaign.mockResolvedValue({
      id: "campaign_new",
      name: "Nova Jornada",
      created_at: "2026-08-15T13:00:00Z",
    });
    mocks.createCharacter.mockResolvedValue({
      ...savedCampaign.characters[0],
      id: "char_new",
      name: "Nova Heroína",
      region_id: null,
      location_id: null,
    });
  });

  it("cria campanha e personagem antes de abrir a tela do jogo", async () => {
    mocks.listCampaigns.mockResolvedValue([]);
    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "CRIAR PERSONAGEM" }),
    );

    fireEvent.change(screen.getByLabelText("Nome da campanha"), {
      target: { value: "  Nova Jornada  " },
    });
    fireEvent.change(screen.getByLabelText("Nome do personagem"), {
      target: { value: "  Nova Heroína  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "CRIAR PERSONAGEM" }));

    await waitFor(() => expect(mocks.createCampaign).toHaveBeenCalledWith("Nova Jornada"));
    expect(mocks.createCharacter).toHaveBeenCalledWith(
      "campaign_new",
      "Nova Heroína",
      null,
    );
    expect(mocks.setSession).toHaveBeenCalledWith("campaign_new", "char_new");
    expect(await screen.findByText("Tela do jogo")).toBeInTheDocument();
  });

  it("permite selecionar uma única afinidade profissional de background", async () => {
    mocks.listCampaigns.mockResolvedValue([]);
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "CRIAR PERSONAGEM" }));
    fireEvent.change(screen.getByLabelText("Nome da campanha"), {
      target: { value: "Nova Jornada" },
    });
    fireEvent.change(screen.getByLabelText("Nome do personagem"), {
      target: { value: "Nova Heroína" },
    });
    fireEvent.change(
      screen.getByLabelText("Experiência profissional na Terra"),
      { target: { value: "CHEF" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "CRIAR PERSONAGEM" }));

    await waitFor(() =>
      expect(mocks.createCharacter).toHaveBeenCalledWith(
        "campaign_new",
        "Nova Heroína",
        "CHEF",
      ),
    );
  });

  it("lista campanhas e continua com o personagem persistido", async () => {
    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "CAMPANHAS" }),
    );

    expect(await screen.findByText("Vale Persistente")).toBeInTheDocument();
    expect(screen.getByText("Logan")).toBeInTheDocument();
    expect(screen.getByText("Level 0")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "JOGAR" }));

    expect(mocks.setSession).toHaveBeenCalledWith("campaign_1", "char_1");
    expect(await screen.findByText("Tela do jogo")).toBeInTheDocument();
  });

  it("exclui uma campanha somente após confirmação", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "CAMPANHAS" }),
    );

    expect(await screen.findByText("Vale Persistente")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(mocks.deleteCampaign).toHaveBeenCalledWith("campaign_1"));
    await waitFor(() => expect(screen.queryByText("Vale Persistente")).not.toBeInTheDocument());
  });

  it("mantém a campanha quando a exclusão é cancelada", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "CAMPANHAS" }),
    );

    expect(await screen.findByText("Vale Persistente")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));

    expect(mocks.deleteCampaign).not.toHaveBeenCalled();
    expect(screen.getByText("Vale Persistente")).toBeInTheDocument();
  });
});
