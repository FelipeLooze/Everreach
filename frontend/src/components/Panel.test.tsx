import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Panel } from "@/components/Panel";

describe("Panel", () => {
  afterEach(cleanup);

  it("preserva fechamento pelo botão e pelo overlay, mas não pelo conteúdo", () => {
    const onClose = vi.fn();
    const { container } = render(
      <Panel title="Personagem" onClose={onClose} size="wide">
        <button>Conteúdo</button>
      </Panel>,
    );

    expect(screen.getByRole("dialog")).toHaveClass("panel-wide");
    expect(screen.getByRole("dialog")).toHaveClass("everreach-frame");
    fireEvent.click(screen.getByRole("button", { name: "Conteúdo" }));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(onClose).toHaveBeenCalledOnce();
    fireEvent.click(container.querySelector(".panel-overlay")!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
