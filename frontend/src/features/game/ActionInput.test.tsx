import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionInput } from "@/features/game/ActionInput";


describe("ActionInput", () => {
  afterEach(cleanup);

  it("envia a técnica explicitamente selecionada junto da descrição", () => {
    const onSubmit = vi.fn();
    render(
      <ActionInput
        disabled={false}
        onSubmit={onSubmit}
        techniques={[
          {
            id: "tech_wind_cut",
            name: "Corte de Vento",
            description: "Integra espada e vento.",
            type: "HYBRID",
            mastery: "BASIC",
          },
        ]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Técnica usada"), {
      target: { value: "tech_wind_cut" },
    });
    fireEvent.change(screen.getByPlaceholderText("Como você usa esta técnica?"), {
      target: { value: "Ataco o alvo de treino." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Agir" }));

    expect(onSubmit).toHaveBeenCalledWith(
      "Ataco o alvo de treino.",
      "tech_wind_cut",
    );
  });

  it("mantém texto livre sem declarar uma técnica", () => {
    const onSubmit = vi.fn();
    render(
      <ActionInput
        disabled={false}
        onSubmit={onSubmit}
        techniques={[]}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("O que você deseja fazer?"), {
      target: { value: "Observo o terreno." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Agir" }));

    expect(onSubmit).toHaveBeenCalledWith("Observo o terreno.", undefined);
  });
});
