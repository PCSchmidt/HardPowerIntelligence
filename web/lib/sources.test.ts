import { describe, expect, it } from "vitest";
import { distinctOutlets, hostOf, sourceName } from "@/lib/sources";
import type { Citation } from "@/lib/types";

function cite(url: string): Citation {
  return {
    id: url,
    source_id: "feeds",
    url,
    fetched_at: "2026-07-06T09:00:00+00:00",
    published_at: "2026-07-06T12:00:00+00:00",
    native_id: "n",
    license_class: "public",
    title: null,
    excerpt: null,
  };
}

describe("hostOf", () => {
  it("returns the bare host, dropping www.", () => {
    expect(hostOf("https://www.navalnews.com/a/b")).toBe("navalnews.com");
    expect(hostOf("https://defensenews.com/x")).toBe("defensenews.com");
  });

  it("returns empty string for a malformed url", () => {
    expect(hostOf("not a url")).toBe("");
    expect(hostOf("")).toBe("");
  });
});

describe("distinctOutlets", () => {
  it("de-duplicates outlets in first-seen order", () => {
    const outlets = distinctOutlets([
      cite("https://www.navalnews.com/a"),
      cite("https://defensenews.com/b"),
      cite("https://www.navalnews.com/c"), // same outlet as the first
    ]);
    expect(outlets).toEqual(["navalnews.com", "defensenews.com"]);
  });

  it("skips citations whose url can't be parsed", () => {
    expect(distinctOutlets([cite("https://navalnews.com/a"), cite("garbage")])).toEqual([
      "navalnews.com",
    ]);
  });
});

describe("sourceName", () => {
  it("maps known source ids to display names and passes through unknowns", () => {
    expect(sourceName("edgar")).toBe("SEC EDGAR");
    expect(sourceName("feeds")).toBe("feeds");
  });
});
