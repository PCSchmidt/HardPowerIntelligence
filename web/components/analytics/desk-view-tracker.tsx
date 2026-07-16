"use client";

import { useEffect, useRef } from "react";

import { capture } from "@/lib/analytics";

// BriefReader is a Server Component, so the desk-view event needs a client seam. Renders nothing.
//
// `fired` guards against React 18/19 StrictMode double-invoking effects in dev, which would
// otherwise double-count every desk view — the kind of quiet inflation that makes early
// engagement numbers look better than they are, right when you're deciding what to build next.
export function DeskViewTracker({
  desk,
  briefDate,
  itemCount,
}: {
  desk: string;
  briefDate: string;
  itemCount: number;
}) {
  const fired = useRef(false);

  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    capture({ name: "desk_viewed", desk, brief_date: briefDate, item_count: itemCount });
  }, [desk, briefDate, itemCount]);

  return null;
}
