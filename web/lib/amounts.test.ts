import { describe, expect, it } from "vitest";
import { classifyAmount, formatUsd, keyAmount, parseAmounts } from "@/lib/amounts";

describe("parseAmounts", () => {
  it("normalizes scaled figures to dollars", () => {
    expect(parseAmounts("a $1.1 billion contract")).toEqual([1.1e9]);
    expect(parseAmounts("$700M and $55.9M")).toEqual([700e6, 55.9e6]);
    expect(parseAmounts("$500K seed")).toEqual([500e3]);
  });

  it("strips thousands separators", () => {
    expect(parseAmounts("$1,250,000 award")).toEqual([1_250_000]);
  });

  it("handles the single-letter trillion abbreviation", () => {
    expect(parseAmounts("a $2T market")).toEqual([2e12]);
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

describe("classifyAmount", () => {
  it("marks committed capital as tracked", () => {
    expect(classifyAmount("Navy awards $1.1B LRASM deal", "")).toEqual({ value: 1.1e9, kind: "tracked" });
    expect(classifyAmount("SK Hynix to invest $28B in expansion", "")).toEqual({ value: 28e9, kind: "tracked" });
    expect(classifyAmount("Solstice acquires Element in $14.5B deal", "")).toEqual({ value: 14.5e9, kind: "tracked" });
  });

  it("marks market-size / forecast figures as projected", () => {
    // The 7/9 offender: an aggregate investment estimate tied to a horizon year.
    expect(classifyAmount("$720B in U.S. grid investment needed by 2030", "")).toEqual({
      value: 720e9,
      kind: "projected",
    });
    expect(classifyAmount("Data-center power market projected to reach $500B by 2032", "")).toEqual({
      value: 500e9,
      kind: "projected",
    });
    expect(classifyAmount("Nuclear SMR total addressable market of $2 trillion", "")).toEqual({
      value: 2e12,
      kind: "projected",
    });
    expect(classifyAmount("Grid capex expected to reach $90B annually", "")).toEqual({
      value: 90e9,
      kind: "projected",
    });
    // A long-horizon aggregate estimate with no explicit "investment" noun, only "needed … by".
    expect(classifyAmount("$500B needed to modernize the grid by 2035", "")).toEqual({
      value: 500e9,
      kind: "projected",
    });
  });

  it("does not flag a real award that merely names a delivery year", () => {
    // A bare future year is a period-of-performance date, not a forecast — must stay tracked.
    expect(classifyAmount("Army awards $3B contract for vehicles delivered by 2031", "")).toEqual({
      value: 3e9,
      kind: "tracked",
    });
  });

  it("classifies from the segment the figure came from", () => {
    // Headline figure is a real award; a projection sits in the body — the headline award wins and stays tracked.
    expect(classifyAmount("DoD awards $1.1B contract", "Analysts see the market reaching $700B by 2030")).toEqual({
      value: 1.1e9,
      kind: "tracked",
    });
    // No headline figure: body's largest figure is classified from the body's own framing.
    expect(classifyAmount("Grid outlook", "Investment is projected to hit $650B by 2035")).toEqual({
      value: 650e9,
      kind: "projected",
    });
  });

  it("is null when there is no figure", () => {
    expect(classifyAmount("no money here", "none here either")).toBeNull();
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
