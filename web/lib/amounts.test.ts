import { describe, expect, it } from "vitest";
import { formatUsd, keyAmount, parseAmounts } from "@/lib/amounts";

describe("parseAmounts", () => {
  it("normalizes scaled figures to dollars", () => {
    expect(parseAmounts("a $1.1 billion contract")).toEqual([1.1e9]);
    expect(parseAmounts("$700M and $55.9M")).toEqual([700e6, 55.9e6]);
    expect(parseAmounts("$500K seed")).toEqual([500e3]);
  });

  it("strips thousands separators", () => {
    expect(parseAmounts("$1,250,000 award")).toEqual([1_250_000]);
  });

  it("returns nothing when there is no dollar figure", () => {
    expect(parseAmounts("no money mentioned here")).toEqual([]);
  });
});

describe("keyAmount", () => {
  it("prefers the first figure in the headline", () => {
    expect(keyAmount("Navy awards $1.1B LRASM deal", "body mentions $9B elsewhere")).toBe(1.1e9);
  });

  it("falls back to the largest figure in the body", () => {
    expect(keyAmount("No number in headline", "two figures: $1M and $5M")).toBe(5e6);
  });

  it("is null when neither headline nor body has a figure", () => {
    expect(keyAmount("nothing", "nothing here either")).toBeNull();
  });
});

describe("formatUsd", () => {
  it("renders compact labels and drops a trailing .0", () => {
    expect(formatUsd(1.5e9)).toBe("$1.5B");
    expect(formatUsd(1e9)).toBe("$1B");
    expect(formatUsd(700e6)).toBe("$700M");
    expect(formatUsd(55.9e6)).toBe("$55.9M");
    expect(formatUsd(500e3)).toBe("$500K");
  });

  it("renders bare dollars below a thousand", () => {
    expect(formatUsd(999)).toBe("$999");
  });
});
