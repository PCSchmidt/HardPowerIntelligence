import { describe, expect, it } from "vitest";
import { deskLabel, entityDisplayName } from "@/lib/entities";

describe("entityDisplayName", () => {
  it("title-cases an all-caps SEC title", () => {
    expect(entityDisplayName("CENTRUS ENERGY CORP")).toBe("Centrus Energy Corp");
  });

  it("leaves a name that already has intentional casing untouched", () => {
    expect(entityDisplayName("D-Wave Quantum Inc.")).toBe("D-Wave Quantum Inc.");
  });
});

describe("deskLabel", () => {
  it("maps known desks to display labels", () => {
    expect(deskLabel("ai")).toBe("AI Infrastructure");
    expect(deskLabel("defense")).toBe("Defense");
    expect(deskLabel("energy")).toBe("Energy");
  });

  it("falls back to the raw value for an unknown desk", () => {
    expect(deskLabel("space")).toBe("space");
  });
});
