import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BriefContent } from "@/components/brief/brief-content";
import type { BriefItem, Citation } from "@/lib/types";

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

function citation(overrides: Partial<Citation>): Citation {
  return {
    id: "c1",
    source_id: "feeds",
    url: "https://www.navalnews.com/some-article",
    fetched_at: "2026-07-06T09:00:00+00:00",
    published_at: "2026-07-06T12:00:00+00:00",
    native_id: "n1",
    license_class: "public",
    title: "Some article",
    excerpt: null,
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

describe("BriefContent source footer (at-a-glance provenance)", () => {
  it("shows distinct outlet domains and the latest publication date", () => {
    render(
      <BriefContent
        items={[item({ id: "1", citation_ids: ["c1", "c2"] })]}
        citations={[
          citation({ id: "c1", url: "https://www.navalnews.com/a", published_at: "2026-07-05T12:00:00+00:00" }),
          citation({ id: "c2", url: "https://defensenews.com/b", published_at: "2026-07-06T12:00:00+00:00" }),
        ]}
        entities={[]}
      />,
    );
    expect(screen.getByText("Sources (2)")).toBeInTheDocument();
    expect(screen.getByText(/navalnews\.com, defensenews\.com/)).toBeInTheDocument();
    // latest of the two publication dates, not the earlier one
    expect(screen.getByText(/Published 7\/6\/2026/)).toBeInTheDocument();
  });

  it("truncates to first two outlets with a +N overflow marker", () => {
    render(
      <BriefContent
        items={[item({ id: "1", citation_ids: ["c1", "c2", "c3"] })]}
        citations={[
          citation({ id: "c1", url: "https://www.navalnews.com/a" }),
          citation({ id: "c2", url: "https://defensenews.com/b" }),
          citation({ id: "c3", url: "https://breakingdefense.com/c" }),
        ]}
        entities={[]}
      />,
    );
    expect(screen.getByText(/navalnews\.com, defensenews\.com \+1/)).toBeInTheDocument();
  });

  it("falls back to Retrieved when no source carries a publication date", () => {
    render(
      <BriefContent
        items={[item({ id: "1", citation_ids: ["c1"] })]}
        citations={[
          citation({ id: "c1", published_at: null, fetched_at: "2026-07-04T08:00:00+00:00" }),
        ]}
        entities={[]}
      />,
    );
    expect(screen.getByText(/Retrieved 7\/4\/2026/)).toBeInTheDocument();
  });
});
