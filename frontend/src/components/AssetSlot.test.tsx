import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AssetSlot } from "@/components/AssetSlot";

describe("AssetSlot", () => {
  afterEach(cleanup);

  it("renders an elegant placeholder glyph when no asset exists yet", () => {
    render(<AssetSlot assetUrl={null} placeholderGlyph="⚔" label="Espada" />);

    expect(screen.getByRole("img", { name: "Espada" })).toBeInTheDocument();
    expect(screen.getByText("⚔")).toBeInTheDocument();
  });

  it("renders the real image once a future asset reference exists", () => {
    render(<AssetSlot assetUrl="https://example.com/espada.png" placeholderGlyph="⚔" label="Espada" />);

    const img = screen.getByRole("img", { name: "Espada" });
    expect(img.tagName).toBe("IMG");
    expect(img).toHaveAttribute("src", "https://example.com/espada.png");
  });

  it("falls back to the placeholder when assetUrl is undefined", () => {
    render(<AssetSlot placeholderGlyph="⚔" label="Espada" />);

    expect(document.querySelector(".asset-slot-placeholder")).toBeInTheDocument();
  });
});
