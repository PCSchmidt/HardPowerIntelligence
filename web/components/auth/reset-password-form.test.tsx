import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const getSession = vi.fn();
const updateUser = vi.fn();
const push = vi.fn();
const refresh = vi.fn();

vi.mock("@/lib/supabase/client", () => ({
  createSupabaseBrowserClient: () => ({ auth: { getSession, updateUser } }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

import { ResetPasswordForm } from "@/components/auth/reset-password-form";

const withSession = () => getSession.mockResolvedValue({ data: { session: { user: {} } } });

async function fill(password: string, confirm: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByPlaceholderText("New password"), password);
  await user.type(screen.getByPlaceholderText("Confirm new password"), confirm);
  await user.click(screen.getByRole("button", { name: /set new password/i }));
  return user;
}

describe("ResetPasswordForm", () => {
  beforeEach(() => {
    getSession.mockReset();
    updateUser.mockReset().mockResolvedValue({ error: null });
    push.mockReset();
  });

  it("sets the password and lands the user in the product", async () => {
    withSession();
    render(<ResetPasswordForm />);

    await fill("a-strong-passphrase", "a-strong-passphrase");

    expect(updateUser).toHaveBeenCalledWith({ password: "a-strong-passphrase" });
    expect(push).toHaveBeenCalledWith("/desk/defense");
  });

  it("rejects a mismatched confirmation without calling Supabase", async () => {
    withSession();
    render(<ResetPasswordForm />);

    await fill("a-strong-passphrase", "a-strong-passphrasf");

    expect(await screen.findByText(/passwords don't match/i)).toBeInTheDocument();
    expect(updateUser).not.toHaveBeenCalled();
  });

  it("rejects a password under the minimum without calling Supabase", async () => {
    withSession();
    render(<ResetPasswordForm />);

    await fill("short", "short");

    // Specific: the always-visible "At least 8 characters." hint also matches a looser regex.
    expect(
      await screen.findByText(/password must be at least 8 characters/i),
    ).toBeInTheDocument();
    expect(updateUser).not.toHaveBeenCalled();
  });

  // Landing here with no session means the code exchange never happened (dead or reused link).
  // Say so up front instead of letting them type a new password twice and fail on submit.
  it("explains a dead link instead of showing an unusable form", async () => {
    getSession.mockResolvedValue({ data: { session: null } });
    render(<ResetPasswordForm />);

    expect(await screen.findByText(/invalid, expired, or already used/i)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("New password")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request a new link/i })).toBeInTheDocument();
  });

  it("surfaces a rejection from Supabase", async () => {
    withSession();
    updateUser.mockResolvedValue({
      error: { message: "New password should be different from the old password." },
    });
    render(<ResetPasswordForm />);

    await fill("a-strong-passphrase", "a-strong-passphrase");

    expect(await screen.findByText(/should be different/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
