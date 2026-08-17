import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsPanel } from "@/features/settings/SettingsPanel";

describe("SettingsPanel", () => {
  afterEach(cleanup);

  it("sai para o menu sem oferecer exclusão da campanha", async () => {
    const onExit = vi.fn();
    render(
      <MemoryRouter initialEntries={["/game"]}>
        <Routes>
          <Route path="/game" element={<SettingsPanel onExit={onExit} />} />
          <Route path="/" element={<p>Menu inicial</p>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByText("Resetar tudo")).not.toBeInTheDocument();
    expect(screen.getByText(/sem apagar a campanha/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sair" }));

    expect(onExit).toHaveBeenCalledOnce();
    expect(await screen.findByText("Menu inicial")).toBeInTheDocument();
  });
});
