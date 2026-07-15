import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const resetPasswordForEmail = vi.fn();

vi.mock("@/lib/supabase/client", () => ({
  createSupabaseBrowserClient: () => ({ auth: { resetPasswordForEmail } }),
}));

import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";

async function submit(email: string) {
  const user = userEvent.setup();
  render(<ForgotPasswordForm />);
  await user.type(screen.getByPlaceholderText(/email/i), email);
  await user.click(screen.getByRole("button", { name: /send reset link/i }));
}

describe("ForgotPasswordForm", () => {
  beforeEach(() => {
    resetPasswordForEmail.mockReset().mockResolvedValue({ error: null });
  });

  it("sends the reset link back through the auth callback, not straight to the page", async () => {
    await submit("operator@hpi.test");

    // /reset-password is useless without the session the callback mints from the code.
    expect(resetPasswordForEmail).toHaveBeenCalledWith("operator@hpi.test", {
      redirectTo: expect.stringContaining("/auth/callback?next=/reset-password"),
    });
  });

  it("confirms dispatch without asserting the account exists", async () => {
    await submit("operator@hpi.test");
    expect(await screen.findByText(/if an account exists/i)).toBeInTheDocument();
  });

  // An unregistered address must be indistinguishable from a registered one, or the form
  // becomes an oracle for enumerating who has an HPI account.
  it("gives an unknown address the identical response", async () => {
    resetPasswordForEmail.mockResolvedValue({
      error: { message: "User not found", status: 400 },
    });

    await submit("nobody@hpi.test");

    expect(await screen.findByText(/if an account exists/i)).toBeInTheDocument();
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });

  it("does surface a genuine transport failure", async () => {
    resetPasswordForEmail.mockResolvedValue({
      error: { message: "Email rate limit exceeded", status: 429 },
    });

    await submit("operator@hpi.test");

    expect(await screen.findByText(/rate limit exceeded/i)).toBeInTheDocument();
    expect(screen.queryByText(/if an account exists/i)).not.toBeInTheDocument();
  });
});
