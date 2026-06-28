import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BriefContent } from "@/components/brief/brief-content";
import type { BriefItem } from "@/lib/types";

function item(overrides: Partial<BriefItem>): BriefItem {
  return {
    id: "1",
    item_type: "filing",
    attribution: "confirmed",
    headline: "Some headline",
    body: "A factual sentence.",
    read: "",
    watch: "",
    entity_ids: [],
    citation_ids: [],
    materiality_score: null,
    display_order: 0,
    ...overrides,
  };
}

describe("BriefContent attribution chip (D099)", () => {
  it("renders the confidence label for each item's tier", () => {
    render(
      <BriefContent
        items={[
          item({ id: "1", headline: "A primary award", attribution: "confirmed" }),
          item({ id: "2", headline: "A reported story", attribution: "reported" }),
          item({ id: "3", headline: "A weak signal", attribution: "speculative" }),
        ]}
        citations={[]}
        entities={[]}
      />,
    );
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(screen.getByText("Reported")).toBeInTheDocument();
    expect(screen.getByText("Speculative")).toBeInTheDocument();
  });

  it("falls back to Confirmed when attribution is missing (pre-D099 items)", () => {
    // Simulate an older payload with no attribution field.
    const legacy = item({ id: "9", headline: "Legacy item" });
    // @ts-expect-error — exercising the runtime fallback for a missing field
    delete legacy.attribution;
    render(<BriefContent items={[legacy]} citations={[]} entities={[]} />);
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
  });
});
