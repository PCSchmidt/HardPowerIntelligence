"""Push a health alert via Resend (D156).

GitHub's native failure email fires on any non-zero exit but is easy to filter out and never says
*why* — the 2026-07-24 billing dark was found via stale reader briefs two days later, not an alert.
This sends a targeted email for **act-now** conditions only (billing exhaustion, running on the
backstop, low runway, or a critical verdict), so those page immediately.

`alert_payload` is pure (decides + formats); `send_resend_alert` is best-effort — a notify failure
returns False and NEVER changes the health verdict or crashes the run."""
from __future__ import annotations

from datetime import date

import httpx

from engine.ops.health import HealthReport

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 15.0

# Warn-level codes that still warrant an out-of-band push (billing conditions the operator must act
# on now, before the next run). A critical verdict always pushes regardless.
_ALERT_CODES = {"billing_exhausted", "running_on_backstop", "credit_runway_low", "balance_check_failed"}


def alert_payload(report: HealthReport, day: date) -> tuple[str, str] | None:
    """Return (subject, body) if the report warrants a push, else None.

    Pushes on a critical verdict, or on any act-now billing code even when the verdict is only
    'degraded' (a warn) — those are the conditions where waiting for the daily manual glance is
    exactly the failure mode D155/D156 exist to prevent."""
    codes = {f.code for f in report.findings}
    if report.verdict != "critical" and not (codes & _ALERT_CODES):
        return None
    subject = f"HPI {report.verdict.upper()} — {report.summary}"
    lines = [f"Run health for {day}: {report.summary}", ""]
    lines += [
        f"[{f.level}] {f.code} — {f.message}"
        for f in report.findings
        if f.level in ("critical", "warn")
    ]
    if report.digest:
        lines += ["", "Digest:"] + [f"- {d}" for d in report.digest]
    return subject, "\n".join(lines)


async def send_resend_alert(
    subject: str,
    body: str,
    *,
    api_key: str,
    to: str,
    sender: str,
    client: httpx.AsyncClient | None = None,
) -> tuple[bool, str]:
    """POST the alert to Resend. Returns ``(ok, detail)``.

    ``detail`` is a human-readable reason so the run log distinguishes the three ways a push can
    fail to land — *config missing* (secret unset), *Resend rejected* (non-2xx, e.g. an
    unverified ``from`` domain), and *transport error* (exception). The original silent ``False``
    hid exactly this: on 2026-07-27 the pager no-op'd on its first real critical event and the log
    said only "skipped/failed", giving no way to tell an unset secret from a rejected sender.
    Best-effort: never raises, never changes the health verdict."""
    if not api_key:
        return False, "skipped: no RESEND_API_KEY set"
    if not to:
        return False, "skipped: no ALERT_EMAIL_TO set"
    if not sender:
        return False, "skipped: no sender configured"
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
    try:
        resp = await client.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": sender, "to": [to], "subject": subject, "text": body},
        )
        if resp.status_code in (200, 201):
            return True, "sent"
        # Resend puts the actionable reason (e.g. domain not verified) in the body — surface it.
        return False, f"resend rejected: HTTP {resp.status_code} {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001 — alerting must never crash the health run
        return False, f"resend transport error: {type(exc).__name__}: {exc}"
    finally:
        if owns_client:
            await client.aclose()
