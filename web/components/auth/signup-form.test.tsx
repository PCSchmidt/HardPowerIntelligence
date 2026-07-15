import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const signUp = vi.fn();
const push = vi.fn();
const refresh = vi.fn();

vi.mock("@/lib/supabase/client", () => ({
  createSupabaseBrowserClient: () => ({ auth: { signUp } }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

import { SignupForm } from "@/components/auth/signup-form";

async function submit(email: string, password: string) {
  const user = userEvent.setup();
  render(<SignupForm />);
  await user.type(screen.getByPlaceholderText(/email/i), email);
  await user.type(screen.getByPlaceholderText(/password/i), password);
  await user.click(screen.getByRole("button", { name: /create account/i }));
}

describe("SignupForm", () => {
  beforeEach(() => {
    signUp.mockReset().mockResolvedValue({ data: { session: null }, error: null });
    push.mockReset();
  });

  it("routes the confirmation link through the auth callback", async () => {
    await submit("analyst@fund.test", "a-strong-passphrase");

    // Straight-to-desk leaves the PKCE code unspent and the user logged out (D141).
    expect(signUp).toHaveBeenCalledWith(
      expect.objectContaining({
        email: "analyst@fund.test",
        options: { emailRedirectTo: expect.stringContaining("/auth/callback?next=/desk/defense") },
      }),
    );
  });

  it("tells the user to confirm by email when no session comes back", async () => {
    await submit("analyst@fund.test", "a-strong-passphrase");
    expect(await screen.findByText(/check your email to confirm/i)).toBeInTheDocument();
  });

  // The signup floor must match the reset floor, or a password accepted here is rejected later.
  it("enforces the same minimum as the reset form, without calling Supabase", async () => {
    await submit("analyst@fund.test", "short");

    expect(
      await screen.findByText(/password must be at least 8 characters/i),
    ).toBeInTheDocument();
    expect(signUp).not.toHaveBeenCalled();
  });

  it("surfaces a Supabase rejection", async () => {
    signUp.mockResolvedValue({
      data: { session: null },
      error: { message: "User already registered" },
    });

    await submit("analyst@fund.test", "a-strong-passphrase");

    expect(await screen.findByText(/already registered/i)).toBeInTheDocument();
  });
});
