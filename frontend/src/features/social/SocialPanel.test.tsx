import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SocialPanel } from "@/features/social/SocialPanel";

const mocks = vi.hoisted(() => ({ getSocialState: vi.fn() }));
vi.mock("@/api/social", () => mocks);

describe("SocialPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows the current group and known organizations", async () => {
    mocks.getSocialState.mockResolvedValue({
      active_group: {
        id: "group_1",
        name: "Companhia da Estrada",
        group_type: "TRAVEL",
        purpose: "Viajar em segurança.",
        members: [
          { actor_type: "CHARACTER", actor_id: "char_1", name: "Logan", leader: true },
          { actor_type: "NPC", actor_id: "npc_1", name: "Mira", leader: false },
        ],
      },
      organizations: [
        {
          id: "org_1",
          name: "Guilda de Aventureiros de Cardal",
          organization_type: "GUILD",
          description: "Publica contratos locais.",
          status: "ACTIVE",
          origin: "NATIVE",
          formality: "FORMAL",
          transported_people_stance: "WELCOMING",
          headquarters_name: "Guilda de Aventureiros de Cardal",
          leader_name: "Ilyra",
          leader_title: "Mestre da Guilda",
          membership: "NON_MEMBER",
          role: null,
          reputation: "RELIABLE",
          active_notices: 2,
          focus: null,
          goal: null,
          goals_achieved: 0,
          relations: [],
        },
        {
          id: "org_2",
          name: "Caçadores do Véu",
          organization_type: "GUILD",
          description: "Guilda de caçadores fundada por Transportados.",
          status: "ACTIVE",
          origin: "TRANSPORTED_CREATED",
          formality: "INFORMAL",
          transported_people_stance: null,
          headquarters_name: null,
          leader_name: "Dessa",
          leader_title: "Mestre da Guilda",
          membership: "MEMBER",
          role: "Oficial",
          reputation: "NEUTRAL",
          active_notices: 0,
          focus: "HUNTERS",
          goal: { description: "Fazer 6 incursões ao ermo.", progress: 2, target: 6 },
          goals_achieved: 1,
          relations: [{ organization_name: "Lobos Cinzentos", relation_type: "RIVAL" }],
        },
      ],
    });

    render(<SocialPanel campaignId="campaign_1" characterId="char_1" />);

    expect(await screen.findByText("Companhia da Estrada")).toBeInTheDocument();
    expect(screen.getByText("Mira")).toBeInTheDocument();
    expect(screen.getAllByText("Guilda de Aventureiros de Cardal")).toHaveLength(2);
    expect(screen.getByText("Confiável")).toBeInTheDocument();
    expect(screen.getByText("Informal")).toBeInTheDocument();
    expect(screen.getByText("Fazer 6 incursões ao ermo. (2/6) — 1 já alcançado(s)")).toBeInTheDocument();
    expect(screen.getByText("Rival de Lobos Cinzentos")).toBeInTheDocument();
    expect(mocks.getSocialState).toHaveBeenCalledWith("campaign_1", "char_1");
  });

  it("keeps empty group and organization states explicit", async () => {
    mocks.getSocialState.mockResolvedValue({ active_group: null, organizations: [] });
    render(<SocialPanel campaignId="campaign_1" characterId="char_1" />);

    expect(await screen.findByText("Você não faz parte de um grupo no momento.")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma organização conhecida neste momento.")).toBeInTheDocument();
  });
});
