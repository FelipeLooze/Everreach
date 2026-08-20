import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StoryLogPanel } from "@/features/game/StoryLogPanel";

describe("StoryLogPanel", () => {
  afterEach(cleanup);

  it("diferencia ações do jogador e narração sem remover o texto", () => {
    render(
      <StoryLogPanel
        error={null}
        entries={[
          { id: "story_1", kind: "player", text: "Olhar em volta", created_at: "2026-08-20T10:00:00Z" },
          { id: "story_2", kind: "narrator", text: "A praça está silenciosa.", created_at: "2026-08-20T10:00:01Z" },
        ]}
      />,
    );

    expect(screen.getByText("> Olhar em volta")).toBeInTheDocument();
    expect(screen.getByText("A praça está silenciosa.")).toBeInTheDocument();
  });
});
