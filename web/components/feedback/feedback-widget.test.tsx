import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// vi.hoisted, not a bare const: vi.mock is hoisted above module scope, and this factory
// dereferences `capture` immediately rather than closing over it lazily.
const { capture } = vi.hoisted(() => ({ capture: vi.fn() }));

vi.mock("@/lib/analytics", () => ({ capture }));
vi.mock("next/navigation", () => ({ usePathname: () => "/desk/defense" }));

import { FeedbackWidget } from "@/components/feedback/feedback-widget";

async function open() {
  const user = userEvent.setup();
  render(<FeedbackWidget />);
  await user.click(screen.getByRole("button", { name: /send feedback/i }));
  return user;
}

describe("FeedbackWidget", () => {
  beforeEach(() => capture.mockReset());

  it("stays out of the way until asked", () => {
    render(<FeedbackWidget />);
    expect(screen.getByRole("button", { name: /send feedback/i })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("captures a one-click response with no note required", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: /^useful$/i }));
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(capture).toHaveBeenCalledWith({
      name: "feedback_submitted",
      sentiment: "useful",
      has_note: false,
      note: "",
      path: "/desk/defense",
    });
    expect(await screen.findByText(/thanks/i)).toBeInTheDocument();
  });

  it("carries the note and the page it was sent from", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: /not useful/i }));
    await user.type(screen.getByRole("textbox"), "Too many items, skipped most.");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(capture).toHaveBeenCalledWith(
      expect.objectContaining({
        sentiment: "not_useful",
        has_note: true,
        note: "Too many items, skipped most.",
        path: "/desk/defense",
      }),
    );
  });

  // Requiring a sentiment is what keeps the event vocabulary meaningful; an empty submit would
  // be noise in the one dataset Phase B depends on.
  it("won't send without a sentiment", async () => {
    const user = await open();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
    await user.type(screen.getByRole("textbox"), "note only");
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
    expect(capture).not.toHaveBeenCalled();
  });
});
