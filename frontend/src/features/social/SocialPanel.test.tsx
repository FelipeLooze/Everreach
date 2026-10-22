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
        },
      ],
    });

    render(<SocialPanel campaignId="campaign_1" characterId="char_1" />);

    expect(await screen.findByText("Companhia da Estrada")).toBeInTheDocument();
    expect(screen.getByText("Mira")).toBeInTheDocument();
    expect(screen.getAllByText("Guilda de Aventureiros de Cardal")).toHaveLength(2);
    expect(screen.getByText("Confiável")).toBeInTheDocument();
    expect(mocks.getSocialState).toHaveBeenCalledWith("campaign_1", "char_1");
  });

  it("keeps empty group and organization states explicit", async () => {
    mocks.getSocialState.mockResolvedValue({ active_group: null, organizations: [] });
    render(<SocialPanel campaignId="campaign_1" characterId="char_1" />);

    expect(await screen.findByText("Você não faz parte de um grupo no momento.")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma organização conhecida neste momento.")).toBeInTheDocument();
  });
});
