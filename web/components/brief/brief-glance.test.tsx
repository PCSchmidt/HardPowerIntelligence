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

describe("BriefGlance tracked vs projected value (D138)", () => {
  function withText(id: string, headline: string): BriefItem {
    return { ...item(id), headline, body: "" };
  }

  it("excludes a market projection from the tracked total", () => {
    render(
      <BriefGlance
        items={[
          withText("1", "SK Hynix to invest $28B in expansion"),
          withText("2", "$720B in U.S. grid investment needed by 2030"),
        ]}
      />,
    );
    // Only the $28B committed deal is summed — the $720B forecast is not tracked capital.
    expect(screen.getByText(/≈\$28B tracked/)).toBeInTheDocument();
    expect(screen.queryByText(/\$748B tracked/)).not.toBeInTheDocument();
    // The projection is still shown, tagged as such.
    expect(screen.getByText(/projected/i)).toBeInTheDocument();
  });

  it("omits the tracked figure entirely when every amount is a projection", () => {
    render(<BriefGlance items={[withText("1", "Data-center power market projected to reach $500B by 2032")]} />);
    expect(screen.queryByText(/tracked/)).not.toBeInTheDocument();
  });
});
