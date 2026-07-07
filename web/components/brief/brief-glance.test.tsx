import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BriefGlance } from "@/components/brief/brief-glance";
import type { BriefItem, Citation } from "@/lib/types";

function item(id: string): BriefItem {
  return {
    id,
    item_type: "filing",
    attribution: "confirmed",
    headline: `Headline ${id}`,
    body: "A factual sentence.",
    read: "",
    watch: "",
    entity_ids: [],
    citation_ids: [],
    materiality_score: null,
    display_order: 0,
  };
}

function cite(id: string, url: string): Citation {
  return {
    id,
    source_id: "feeds",
    url,
    fetched_at: "2026-07-06T09:00:00+00:00",
    published_at: "2026-07-06T12:00:00+00:00",
    native_id: id,
    license_class: "public",
    title: null,
    excerpt: null,
  };
}

describe("BriefGlance source count (D131)", () => {
  it("shows the count of distinct outlets, not the raw citation count", () => {
    render(
      <BriefGlance
        items={[item("1"), item("2")]}
        citations={[
          cite("c1", "https://www.navalnews.com/a"),
          cite("c2", "https://defensenews.com/b"),
          cite("c3", "https://www.navalnews.com/c"), // 3rd citation, but same outlet as c1
        ]}
      />,
    );
    // 2 distinct outlets across 3 citations
    expect(screen.getByText(/2 sources/)).toBeInTheDocument();
  });

  it("omits the source count when no citations are supplied", () => {
    render(<BriefGlance items={[item("1")]} />);
    expect(screen.queryByText(/sources/)).not.toBeInTheDocument();
  });
});
