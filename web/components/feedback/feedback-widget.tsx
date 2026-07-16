"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { MessageSquare, ThumbsDown, ThumbsUp, X } from "lucide-react";

import { capture } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Sentiment = "useful" | "not_useful";

// The in-product half of B1. Behavioural events tell us what a reader DID; this catches the "why"
// while they're still in front of the thing, instead of relying on recall in an interview a week
// later. One click is the whole commitment — the note is optional on purpose, because requiring
// prose is what turns a 90%-response affordance into a 5% one.
export function FeedbackWidget() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [sentiment, setSentiment] = useState<Sentiment | null>(null);
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);

  function submit(s: Sentiment) {
    capture({
      name: "feedback_submitted",
      sentiment: s,
      has_note: note.trim().length > 0,
      note: note.trim(),
      path: pathname ?? "",
    });
    setSent(true);
  }

  function close() {
    setOpen(false);
    // Reset only after the panel is gone, so the "thanks" state isn't seen collapsing.
    setTimeout(() => {
      setSent(false);
      setSentiment(null);
      setNote("");
    }, 200);
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Send feedback"
        className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2.5 text-ui-sm font-medium text-foreground shadow-md transition-colors hover:bg-accent"
      >
        <MessageSquare size={15} />
        Feedback
      </button>
    );
  }

  return (
    <div
      role="dialog"
      aria-label="Send feedback"
      className="fixed bottom-5 right-5 z-40 w-[min(20rem,calc(100vw-2.5rem))] rounded-xl border border-border bg-card p-4 shadow-lg"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-ui-md font-medium text-foreground">
          {sent ? "Thanks — that helps." : "How was this brief?"}
        </p>
        <button
          type="button"
          onClick={close}
          aria-label="Close feedback"
          className="-mr-1 -mt-1 rounded p-1 text-muted-foreground hover:text-foreground"
        >
          <X size={15} />
        </button>
      </div>

      {sent ? (
        <p className="mt-2 text-ui-sm text-muted-foreground">
          Every response is read. Tell us more anytime at{" "}
          <a href="mailto:feedback@hardpowerintel.com" className="text-primary hover:underline">
            feedback@hardpowerintel.com
          </a>
          .
        </p>
      ) : (
        <>
          <div className="mt-3 flex gap-2">
            {(
              [
                { key: "useful", label: "Useful", Icon: ThumbsUp },
                { key: "not_useful", label: "Not useful", Icon: ThumbsDown },
              ] as const
            ).map(({ key, label, Icon }) => (
              <button
                key={key}
                type="button"
                onClick={() => setSentiment(key)}
                aria-pressed={sentiment === key}
                className={cn(
                  "inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-ui-sm font-medium transition-colors",
                  sentiment === key
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-accent",
                )}
              >
                <Icon size={14} />
                {label}
              </button>
            ))}
          </div>

          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What did you skip? What was missing? (optional)"
            rows={3}
            className="mt-3 w-full resize-none rounded-md border border-input bg-background px-2.5 py-2 text-ui-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />

          <Button
            size="sm"
            className="mt-2 w-full"
            disabled={!sentiment}
            onClick={() => sentiment && submit(sentiment)}
          >
            Send
          </Button>
        </>
      )}
    </div>
  );
}
