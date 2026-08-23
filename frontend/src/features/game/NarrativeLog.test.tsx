import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { NarrativeLog } from "@/features/game/NarrativeLog";

describe("NarrativeLog", () => {
  afterEach(cleanup);

  it("mostra a mensagem de história vazia quando não há entradas e nada está pendente", () => {
    render(<NarrativeLog entries={[]} />);
    expect(screen.getByText("A história ainda não começou.")).toBeInTheDocument();
  });

  it("mostra o indicador de 'pensando' quando uma resposta está pendente", () => {
    render(<NarrativeLog entries={[]} pending />);
    expect(screen.queryByText("A história ainda não começou.")).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "O narrador está respondendo" })).toBeInTheDocument();
  });

  it("mostra o indicador de 'pensando' após as entradas existentes, sem escondê-las", () => {
    render(
      <NarrativeLog
        entries={[{ id: "1", kind: "player", text: "Olá" }]}
        pending
      />,
    );
    expect(screen.getByText(/Olá/)).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "O narrador está respondendo" })).toBeInTheDocument();
  });

  it("não mostra o indicador quando não há nada pendente", () => {
    render(<NarrativeLog entries={[{ id: "1", kind: "narrator", text: "Bom dia." }]} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
