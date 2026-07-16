import posthog from "posthog-js";

// Product instrumentation (B1). Light and privacy-respecting, by three rules:
//
//  1. NO PII LEAVES THE APP. We identify a reader by their Supabase user UUID and nothing else —
//     never email. The UUID→person join lives in our own DB, so we keep every question we can ask
//     while PostHog holds no identifying data. Cost of this choice: you must join locally to know
//     *who* a session was. That's the right trade for a product whose pitch is provenance.
//  2. NO QUERY STRINGS, EVER. /auth/callback carries single-use PKCE codes and recovery tokens in
//     its URL. A default pageview capture would ship those to a third party. Every URL is stripped
//     to origin+pathname before it leaves (see `stripQuery` + `sanitize_properties`).
//  3. NO BLANKET CAPTURE. autocapture and session recording are off. Every event here is declared
//     and deliberate, so the data means something and we can explain exactly what we collect.
//
// Unconfigured builds are SILENT, not broken: `NEXT_PUBLIC_POSTHOG_KEY` shipped as the literal
// placeholder "phc_..." for months, so anything that isn't a plausible key disables analytics
// rather than throwing on a live site.

const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST;

let started = false;

export function analyticsConfigured(): boolean {
  return Boolean(KEY && KEY.startsWith("phc_") && KEY.length >= 20 && HOST);
}

/** Reduce any URL to origin + pathname. Defends rule 2 above. */
export function stripQuery(url: string): string {
  try {
    const u = new URL(url);
    return `${u.origin}${u.pathname}`;
  } catch {
    return url.split("?")[0].split("#")[0];
  }
}

export function initAnalytics(): void {
  if (started || !analyticsConfigured() || typeof window === "undefined") return;
  started = true;
  posthog.init(KEY!, {
    api_host: HOST,
    // Anonymous visitors create no person record; only signed-in readers do.
    person_profiles: "identified_only",
    autocapture: false,
    disable_session_recording: true,
    capture_pageview: false, // captured manually, with the URL stripped first
    capture_pageleave: true, // needed to tell "read it" from "opened and bounced"
    respect_dnt: true,
    sanitize_properties: (props) => {
      for (const k of ["$current_url", "$referrer", "$initial_current_url", "$initial_referrer"]) {
        if (typeof props[k] === "string") props[k] = stripQuery(props[k] as string);
      }
      return props;
    },
  });
}

/** Identify by Supabase UUID only. Never pass an email address here. */
export function identify(userId: string): void {
  if (!analyticsConfigured() || !started) return;
  posthog.identify(userId);
}

export function resetIdentity(): void {
  if (!analyticsConfigured() || !started) return;
  posthog.reset();
}

export function capturePageview(pathname: string): void {
  if (!analyticsConfigured() || !started || typeof window === "undefined") return;
  posthog.capture("$pageview", { $current_url: `${window.location.origin}${pathname}` });
}

// The declared event vocabulary. `item_sources_opened` is the one that matters most: HPI's whole
// claim is cited provenance, so whether readers actually open the sources is the difference
// between the moat being real and being decoration.
export type AnalyticsEvent =
  | { name: "desk_viewed"; desk: string; brief_date: string; item_count: number }
  | { name: "wire_viewed"; desk: string; item_count: number }
  | { name: "wire_item_clicked"; desk: string; source_id: string; position: number }
  | { name: "item_sources_opened"; desk: string; item_type: string; citation_count: number; position: number }
  | { name: "item_analysis_expanded"; desk: string; item_type: string; position: number }
  | { name: "feedback_submitted"; sentiment: "useful" | "not_useful"; has_note: boolean; note: string; path: string };

export function capture(event: AnalyticsEvent): void {
  if (!analyticsConfigured() || !started) return;
  const { name, ...props } = event;
  posthog.capture(name, props);
}
