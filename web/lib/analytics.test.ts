import { describe, expect, it } from "vitest";

import { analyticsConfigured, stripQuery } from "@/lib/analytics";

describe("stripQuery", () => {
  // The reason this function exists: /auth/callback carries single-use PKCE codes and recovery
  // tokens in the query string. A default pageview capture would ship those to a third party.
  it("strips the auth code from a callback URL", () => {
    expect(stripQuery("https://hardpowerintel.com/auth/callback?code=super-secret&next=/x")).toBe(
      "https://hardpowerintel.com/auth/callback",
    );
  });

  it("strips recovery tokens from a hash as well as a query", () => {
    expect(
      stripQuery("https://hardpowerintel.com/reset-password#access_token=abc&type=recovery"),
    ).toBe("https://hardpowerintel.com/reset-password");
  });

  it("leaves a clean URL untouched and is idempotent", () => {
    const clean = "https://hardpowerintel.com/desk/defense";
    expect(stripQuery(clean)).toBe(clean);
    expect(stripQuery(stripQuery(clean))).toBe(clean);
  });

  it("degrades sensibly on a non-URL string rather than throwing", () => {
    expect(stripQuery("/desk/energy?tab=wire")).toBe("/desk/energy");
    expect(stripQuery("not a url")).toBe("not a url");
  });
});

describe("analyticsConfigured", () => {
  // NEXT_PUBLIC_POSTHOG_KEY shipped as the literal placeholder "phc_..." for months. An
  // unconfigured build must be silent, not broken — the site is live.
  it("treats the shipped placeholder as unconfigured", () => {
    // The test env carries no real key, so this is the placeholder/absent path.
    expect(analyticsConfigured()).toBe(false);
  });

  it("never throws when unconfigured — capture is a no-op", async () => {
    const { capture, identify, capturePageview, initAnalytics, resetIdentity } = await import(
      "@/lib/analytics"
    );
    expect(() => initAnalytics()).not.toThrow();
    expect(() => identify("user-uuid")).not.toThrow();
    expect(() => resetIdentity()).not.toThrow();
    expect(() => capturePageview("/desk/defense")).not.toThrow();
    expect(() =>
      capture({ name: "desk_viewed", desk: "defense", brief_date: "2026-07-15", item_count: 20 }),
    ).not.toThrow();
  });
});
