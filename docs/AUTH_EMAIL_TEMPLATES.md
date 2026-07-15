# Auth email templates

The two emails every HPI reader sees before they ever see a brief. Supabase's stock templates
("Follow this link to confirm your user") are functional and read like a database default — a poor
first impression for a product pitched at analysts who are being asked to trust its provenance.

**These live in the Supabase dashboard, not in this repo** — Auth → Emails → Templates. This file
is the source of truth for what *should* be pasted there. If you edit a template in the dashboard,
update it here too, or the next person will have no idea what production actually sends.

Supabase renders these with Go templates. Available variables:

| Variable | Meaning |
|---|---|
| `{{ .ConfirmationURL }}` | The action link (already points at `/auth/callback`, per URL Configuration) |
| `{{ .Email }}` | The recipient's address |
| `{{ .SiteURL }}` | Site URL from Auth → URL Configuration |
| `{{ .Token }}` | 6-digit OTP — unused by HPI |

Design constraints, learned the hard way by the whole industry:

- **Inline CSS only.** Gmail strips `<style>` blocks.
- **Always include the raw URL as text.** Many clients disable buttons; a link the reader can
  paste is the difference between a working reset and a support email.
- **Keep the "if you didn't request this" line.** It's a trust signal and an anti-phishing norm.
- **No images.** They block by default, cost you nothing to omit, and an image-free email from a
  young sending domain looks less like marketing to spam filters.

---

## Confirm signup

Subject: `Confirm your Hard Power Intelligence account`

```html
<div style="margin:0;padding:24px;background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e3e6ea;border-radius:10px;padding:32px;">
    <div style="font-size:11px;letter-spacing:.14em;font-weight:700;color:#8a94a6;text-transform:uppercase;">
      Hard Power Intelligence
    </div>
    <h1 style="margin:18px 0 10px;font-size:21px;line-height:1.3;color:#12181f;font-weight:700;">
      Confirm your account
    </h1>
    <p style="margin:0 0 22px;font-size:15px;line-height:1.6;color:#414b58;">
      One click and you're in — today's cited brief across the Defense, AI, and Energy desks.
    </p>
    <a href="{{ .ConfirmationURL }}"
       style="display:inline-block;background:#12181f;color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;padding:12px 22px;border-radius:7px;">
      Confirm my account
    </a>
    <p style="margin:24px 0 6px;font-size:13px;line-height:1.5;color:#6b7482;">
      Or paste this into your browser:
    </p>
    <p style="margin:0 0 24px;font-size:12px;line-height:1.5;word-break:break-all;">
      <a href="{{ .ConfirmationURL }}" style="color:#3f6ad8;">{{ .ConfirmationURL }}</a>
    </p>
    <hr style="border:0;border-top:1px solid #e9ecf0;margin:0 0 16px;">
    <p style="margin:0;font-size:12px;line-height:1.5;color:#8a94a6;">
      This link can be used once and expires in 24 hours. If you didn't create an account with
      Hard Power Intelligence, you can safely ignore this message.
    </p>
  </div>
</div>
```

---

## Reset password

Subject: `Reset your Hard Power Intelligence password`

```html
<div style="margin:0;padding:24px;background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e3e6ea;border-radius:10px;padding:32px;">
    <div style="font-size:11px;letter-spacing:.14em;font-weight:700;color:#8a94a6;text-transform:uppercase;">
      Hard Power Intelligence
    </div>
    <h1 style="margin:18px 0 10px;font-size:21px;line-height:1.3;color:#12181f;font-weight:700;">
      Reset your password
    </h1>
    <p style="margin:0 0 22px;font-size:15px;line-height:1.6;color:#414b58;">
      We received a request to reset the password for
      <strong style="color:#12181f;">{{ .Email }}</strong>. Choose a new one below.
    </p>
    <a href="{{ .ConfirmationURL }}"
       style="display:inline-block;background:#12181f;color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;padding:12px 22px;border-radius:7px;">
      Choose a new password
    </a>
    <p style="margin:24px 0 6px;font-size:13px;line-height:1.5;color:#6b7482;">
      Or paste this into your browser:
    </p>
    <p style="margin:0 0 24px;font-size:12px;line-height:1.5;word-break:break-all;">
      <a href="{{ .ConfirmationURL }}" style="color:#3f6ad8;">{{ .ConfirmationURL }}</a>
    </p>
    <hr style="border:0;border-top:1px solid #e9ecf0;margin:0 0 16px;">
    <p style="margin:0;font-size:12px;line-height:1.5;color:#8a94a6;">
      This link can be used once and expires in one hour. If you didn't request a password reset,
      ignore this message — your password won't change.
    </p>
  </div>
</div>
```

---

## After pasting

1. Send yourself one of each (sign up with a spare address; use "Forgot password?" on it).
2. Check **Resend → Emails** for `Delivered`, and check the actual inbox — delivered and
   *in the inbox* are different claims.
3. Read it on a phone. Most first reads are on a phone.

## Related settings

- **Auth → Sign In / Providers → Email → Minimum password length**: set to **8**, matching
  `web/lib/auth.ts`. The client-side check is UX only; this is the real floor.
- **Auth → Rate Limits → emails**: capped Supabase-side. The binding constraint is Resend's free
  tier (~100/day), not this number.
