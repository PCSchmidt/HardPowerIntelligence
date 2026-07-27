"""Resend health-alert notifier (D156). Pure gating + HTTP path via httpx.MockTransport."""
from datetime import date

import httpx
import pytest

from engine.ops.health import Finding, HealthReport
from engine.ops.notify import alert_payload, send_resend_alert

DAY = date(2026, 7, 25)


def _report(verdict, findings):
    return HealthReport(verdict=verdict, findings=findings, summary=f"{verdict} test", digest=["d1"])


class TestAlertPayload:
    def test_critical_verdict_pushes(self):
        r = _report("critical", [Finding("critical", "no_brief_published", "x")])
        assert alert_payload(r, DAY) is not None

    def test_billing_code_at_warn_pushes(self):
        # A warn-level billing condition must still page — waiting for the manual glance is the
        # exact failure D156 prevents.
        r = _report("degraded", [Finding("warn", "running_on_backstop", "x")])
        assert alert_payload(r, DAY) is not None

    def test_ok_does_not_push(self):
        assert alert_payload(_report("ok", []), DAY) is None

    def test_degraded_without_billing_does_not_push(self):
        # Ordinary degradation (thin brief) already rides GitHub's failure email; don't double-page.
        r = _report("degraded", [Finding("warn", "brief_thin", "x")])
        assert alert_payload(r, DAY) is None

    def test_subject_and_body_shape(self):
        r = _report("critical", [Finding("critical", "billing_exhausted", "dry")])
        subject, body = alert_payload(r, DAY)
        assert "CRITICAL" in subject
        assert "billing_exhausted" in body and "Digest" in body


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
class TestSendResendAlert:
    async def test_missing_config_skips_with_reason(self):
        ok, detail = await send_resend_alert("s", "b", api_key="", to="a@b.c", sender="f")
        assert ok is False and "RESEND_API_KEY" in detail
        ok, detail = await send_resend_alert("s", "b", api_key="k", to="", sender="f")
        assert ok is False and "ALERT_EMAIL_TO" in detail
        ok, detail = await send_resend_alert("s", "b", api_key="k", to="a@b.c", sender="")
        assert ok is False and "sender" in detail

    async def test_2xx_returns_true_and_sends_bearer(self):
        def handler(req):
            assert req.headers["Authorization"] == "Bearer k"
            return httpx.Response(200, json={"id": "e1"})

        async with _client(handler) as c:
            ok, detail = await send_resend_alert("s", "b", api_key="k", to="a@b.c", sender="f", client=c)
        assert ok is True and detail == "sent"

    async def test_non_2xx_returns_false_with_status(self):
        async with _client(lambda req: httpx.Response(422, json={"message": "domain not verified"})) as c:
            ok, detail = await send_resend_alert("s", "b", api_key="k", to="a@b.c", sender="f", client=c)
        assert ok is False and "422" in detail and "domain not verified" in detail

    async def test_exception_returns_false_with_type(self):
        def handler(req):
            raise httpx.ConnectError("boom")

        async with _client(handler) as c:
            ok, detail = await send_resend_alert("s", "b", api_key="k", to="a@b.c", sender="f", client=c)
        assert ok is False and "ConnectError" in detail
