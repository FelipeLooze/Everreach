import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UndoLastAction } from "@/features/game/UndoLastAction";

describe("UndoLastAction", () => {
  afterEach(cleanup);

  it("exige motivo e confirmação explícita antes de desfazer", async () => {
    const onUndo = vi.fn().mockResolvedValue(true);
    render(
      <UndoLastAction
        actionText="Deixar a pedra no chão"
        disabled={false}
        onUndo={onUndo}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Desfazer última ação" }));
    expect(screen.getByText(/restaurará o estado anterior/i)).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Confirmar desfazer" });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Por que esta ação deve ser desfeita?"), {
      target: { value: "O item deveria continuar no inventário." },
    });
    fireEvent.click(confirm);

    await waitFor(() =>
      expect(onUndo).toHaveBeenCalledWith("O item deveria continuar no inventário."),
    );
    expect(screen.getByRole("button", { name: "Desfazer última ação" })).toBeInTheDocument();
  });

  it("mantém a confirmação aberta quando o backend recusa o desfazer", async () => {
    const onUndo = vi.fn().mockResolvedValue(false);
    render(<UndoLastAction actionText="Esperar" disabled={false} onUndo={onUndo} />);

    fireEvent.click(screen.getByRole("button", { name: "Desfazer última ação" }));
    fireEvent.change(screen.getByLabelText("Por que esta ação deve ser desfeita?"), {
      target: { value: "Resultado incorreto." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar desfazer" }));

    await waitFor(() => expect(onUndo).toHaveBeenCalled());
    expect(screen.getByLabelText("Por que esta ação deve ser desfeita?")).toBeInTheDocument();
  });
});
