import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const getUser = vi.fn();

vi.mock("@supabase/ssr", () => ({
  createServerClient: () => ({ auth: { getUser } }),
}));

const { proxy } = await import("./proxy");

const signedIn = () => getUser.mockResolvedValue({ data: { user: { id: "u1" } } });
const signedOut = () => getUser.mockResolvedValue({ data: { user: null } });

const go = (path: string) => proxy(new NextRequest(`https://hpi.test${path}`));
const locationOf = (res: Awaited<ReturnType<typeof proxy>>) => res.headers.get("location");

describe("proxy auth gating", () => {
  it("sends an anonymous visitor from a gated desk to login, preserving the destination", async () => {
    signedOut();
    expect(locationOf(await go("/desk/defense"))).toBe(
      "https://hpi.test/login?next=%2Fdesk%2Fdefense",
    );
  });

  it("bounces a signed-in user off login and signup", async () => {
    signedIn();
    expect(locationOf(await go("/login"))).toBe("https://hpi.test/desk/defense");
    expect(locationOf(await go("/signup"))).toBe("https://hpi.test/desk/defense");
  });

  it("bounces a signed-in user off forgot-password", async () => {
    signedIn();
    expect(locationOf(await go("/forgot-password"))).toBe("https://hpi.test/desk/defense");
  });

  // THE deadlock guard (D141). A recovery link signs the user in *before* they pick a new
  // password. If /reset-password ever joins AUTH_ROUTES, that session bounces them to the desk
  // and the password becomes unchangeable — silently re-breaking the whole flow.
  it("lets a signed-in user reach /reset-password — the recovery session must not bounce", async () => {
    signedIn();
    expect(locationOf(await go("/reset-password"))).toBeNull();
  });

  it("lets an anonymous visitor reach the recovery routes", async () => {
    signedOut();
    expect(locationOf(await go("/forgot-password"))).toBeNull();
    expect(locationOf(await go("/reset-password"))).toBeNull();
  });

  it("never intercepts the auth callback in either state", async () => {
    signedOut();
    expect(locationOf(await go("/auth/callback?code=x"))).toBeNull();
    signedIn();
    expect(locationOf(await go("/auth/callback?code=x"))).toBeNull();
  });
});
