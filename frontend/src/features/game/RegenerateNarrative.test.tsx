import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RegenerateNarrative } from "@/features/game/RegenerateNarrative";

describe("RegenerateNarrative", () => {
  afterEach(cleanup);

  it("solicita feedback antes de regenerar", async () => {
    const onRegenerate = vi.fn().mockResolvedValue(true);
    render(<RegenerateNarrative disabled={false} onRegenerate={onRegenerate} />);

    fireEvent.click(screen.getByRole("button", { name: "Regenerar última mensagem" }));
    fireEvent.change(screen.getByLabelText("O que deve mudar na última mensagem?"), {
      target: { value: "Deixe a resposta mais curta." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Regenerar" }));

    await waitFor(() => expect(onRegenerate).toHaveBeenCalledWith("Deixe a resposta mais curta."));
    expect(screen.getByRole("button", { name: "Regenerar última mensagem" })).toBeInTheDocument();
  });

  it("mantém o formulário aberto quando a regeneração falha", async () => {
    const onRegenerate = vi.fn().mockResolvedValue(false);
    render(<RegenerateNarrative disabled={false} onRegenerate={onRegenerate} />);

    fireEvent.click(screen.getByRole("button", { name: "Regenerar última mensagem" }));
    fireEvent.change(screen.getByLabelText("O que deve mudar na última mensagem?"), {
      target: { value: "Não invente uma fala." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Regenerar" }));

    await waitFor(() => expect(onRegenerate).toHaveBeenCalled());
    expect(screen.getByLabelText("O que deve mudar na última mensagem?")).toBeInTheDocument();
  });
});
