"use client";

import { useEffect, useState } from "react";
import { ChevronDown, FileText, Sparkles, X } from "lucide-react";

// First-run orientation for the reader. A brief is dense — a cited ledger, an expandable
// analysis layer, convergence chips — and a first-time tester gets none of that for free.
// This is a one-time, dismissible legend that points at the real affordances so they learn
// by recognizing what's already on screen. Dismissal persists in localStorage; it never
// reappears for that browser. Client-only (localStorage), gated on mount so a returning
// reader who already dismissed it never sees a flash.

const STORAGE_KEY = "hpi.reader.oriented";

export function ReaderOnboarding() {
  // null = not yet checked (SSR + first paint). Once mounted we read localStorage and
  // decide; this avoids hydration mismatch and the dismissed-then-flash problem.
  const [show, setShow] = useState<boolean | null>(null);

  useEffect(() => {
    try {
      setShow(window.localStorage.getItem(STORAGE_KEY) !== "1");
    } catch {
      // Private mode / storage disabled — show once, just don't persist.
      setShow(true);
    }
  }, []);

  function dismiss() {
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // No-op: still hide for this session.
    }
    setShow(false);
  }

  if (!show) return null;

  return (
    <section
      aria-label="How to read this brief"
      className="mb-6 rounded-lg border border-brand-secondary/30 bg-muted/40 p-4 sm:p-5"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-display-sm text-foreground">New here?</h2>
          <p className="mt-0.5 text-ui-sm text-muted-foreground">
            Three things worth knowing about how to read this brief.
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss orientation"
          className="-mr-1 -mt-1 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X size={16} />
        </button>
      </div>

      <ul className="space-y-3">
        <li className="flex items-start gap-3">
          <span className="mt-0.5 inline-flex h-4 min-w-4 shrink-0 items-center justify-center rounded-sm bg-primary/10 px-1 text-[0.65rem] font-medium text-primary">
            1
          </span>
          <p className="text-ui-md text-foreground">
            <span className="font-medium">Every claim is cited.</span>{" "}
            <span className="text-muted-foreground">
              Tap a superscript number or{" "}
              <span className="inline-flex items-center gap-1 align-baseline font-medium text-primary">
                <FileText size={13} className="shrink-0" />
                Sources
              </span>{" "}
              to open the exact public award or filing it came from.
            </span>
          </p>
        </li>

        <li className="flex items-start gap-3">
          <ChevronDown size={16} className="mt-0.5 shrink-0 text-brand-secondary" />
          <p className="text-ui-md text-foreground">
            <span className="font-medium">Analysis stays separate.</span>{" "}
            <span className="text-muted-foreground">
              Expand{" "}
              <span className="font-medium text-brand-secondary">Analysis — HPI interpretation</span>{" "}
              for our read and what to watch — kept distinct from the cited facts.
            </span>
          </p>
        </li>

        <li className="flex items-start gap-3">
          <Sparkles size={16} className="mt-0.5 shrink-0 text-brand-secondary" />
          <p className="text-ui-md text-foreground">
            <span className="font-medium">Convergence chips.</span>{" "}
            <span className="text-muted-foreground">
              A company chip marked with a spark is moving across more than one desk — defense,
              energy, or AI infrastructure.
            </span>
          </p>
        </li>
      </ul>

      <button
        type="button"
        onClick={dismiss}
        className="mt-4 rounded-md bg-primary px-3 py-1.5 text-ui-sm font-medium text-primary-foreground hover:bg-primary/80"
      >
        Got it
      </button>
    </section>
  );
}
