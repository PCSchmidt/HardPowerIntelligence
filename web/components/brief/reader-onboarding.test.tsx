import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReaderOnboarding } from "@/components/brief/reader-onboarding";

const STORAGE_KEY = "hpi.reader.oriented";

describe("ReaderOnboarding", () => {
  it("orients a first-time reader with the three core affordances", async () => {
    render(<ReaderOnboarding />);

    expect(
      await screen.findByRole("region", { name: /how to read this brief/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/every claim is cited/i)).toBeInTheDocument();
    expect(screen.getByText(/analysis stays separate/i)).toBeInTheDocument();
    expect(screen.getByText(/convergence chips/i)).toBeInTheDocument();
  });

  it("persists dismissal and hides when the reader clicks Got it", async () => {
    render(<ReaderOnboarding />);
    const region = await screen.findByRole("region", { name: /how to read this brief/i });

    await userEvent.click(screen.getByRole("button", { name: /got it/i }));

    expect(region).not.toBeInTheDocument();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("1");
  });

  it("persists dismissal from the close (X) control too", async () => {
    render(<ReaderOnboarding />);
    await screen.findByRole("region", { name: /how to read this brief/i });

    await userEvent.click(screen.getByRole("button", { name: /dismiss orientation/i }));

    expect(screen.queryByRole("region", { name: /how to read this brief/i })).not.toBeInTheDocument();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("1");
  });

  it("does not reappear once dismissed", async () => {
    window.localStorage.setItem(STORAGE_KEY, "1");
    render(<ReaderOnboarding />);

    // The mount effect reads localStorage; flush it, then confirm nothing rendered.
    await Promise.resolve();
    expect(
      screen.queryByRole("region", { name: /how to read this brief/i }),
    ).not.toBeInTheDocument();
  });
});
