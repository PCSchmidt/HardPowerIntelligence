import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const exchangeCodeForSession = vi.fn();

vi.mock("@/lib/supabase/server", () => ({
  createSupabaseServerClient: async () => ({ auth: { exchangeCodeForSession } }),
}));

const { GET } = await import("./route");

function callback(query: string) {
  return GET(new NextRequest(`https://hpi.test/auth/callback${query}`));
}

describe("/auth/callback", () => {
  beforeEach(() => {
    exchangeCodeForSession.mockReset().mockResolvedValue({ error: null });
  });

  it("exchanges the code and forwards to the requested destination", async () => {
    const res = await callback("?code=abc123&next=/reset-password");

    expect(exchangeCodeForSession).toHaveBeenCalledWith("abc123");
    expect(res.headers.get("location")).toBe("https://hpi.test/reset-password");
  });

  it("defaults to the desk when no destination is given", async () => {
    const res = await callback("?code=abc123");
    expect(res.headers.get("location")).toBe("https://hpi.test/desk/defense");
  });

  // The `next` value travels in a URL we email out, so an unvalidated redirect here would let
  // an attacker bounce a just-authenticated user to a lookalike site.
  it.each([
    ["absolute off-site URL", "?code=abc123&next=https://evil.test/steal"],
    ["protocol-relative URL", "?code=abc123&next=//evil.test/steal"],
    ["non-path value", "?code=abc123&next=evil.test"],
  ])("refuses an off-site redirect: %s", async (_label, query) => {
    const res = await callback(query);
    expect(res.headers.get("location")).toBe("https://hpi.test/desk/defense");
  });

  it("sends an expired or already-used link back to login with an explanation", async () => {
    exchangeCodeForSession.mockResolvedValue({ error: { message: "invalid grant" } });

    const res = await callback("?code=stale");
    const location = res.headers.get("location") ?? "";

    expect(location).toContain("/login?error=");
    expect(decodeURIComponent(location)).toMatch(/expired or was already used/i);
  });

  it("surfaces an error handed back by Supabase without attempting an exchange", async () => {
    const res = await callback("?error=access_denied&error_description=Email+link+is+invalid");

    expect(exchangeCodeForSession).not.toHaveBeenCalled();
    expect(decodeURIComponent(res.headers.get("location") ?? "")).toContain(
      "Email link is invalid",
    );
  });

  it("handles a link arriving with no code at all", async () => {
    const res = await callback("");

    expect(exchangeCodeForSession).not.toHaveBeenCalled();
    expect(res.headers.get("location") ?? "").toContain("/login?error=");
  });
});
