import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StateBadge } from "@/components/StateBadge";

describe("StateBadge", () => {
  afterEach(cleanup);

  it("renders the label", () => {
    render(<StateBadge tone="danger" label="Danificado" />);

    expect(screen.getByText("Danificado")).toBeInTheDocument();
  });

  it("applies a tone-specific class so danger/warning/success are never distinguished by color alone", () => {
    const { rerender, container } = render(<StateBadge tone="danger" label="x" />);
    expect(container.querySelector(".state-badge-danger")).toBeInTheDocument();

    rerender(<StateBadge tone="warning" label="x" />);
    expect(container.querySelector(".state-badge-warning")).toBeInTheDocument();

    rerender(<StateBadge tone="success" label="x" />);
    expect(container.querySelector(".state-badge-success")).toBeInTheDocument();
  });

  it("always renders a glyph alongside the label, never color alone", () => {
    render(<StateBadge tone="uncertain" label="Incerto" />);

    expect(document.querySelector(".state-badge-glyph")).toHaveTextContent("?");
  });
});
