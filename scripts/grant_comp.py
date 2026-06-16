"""Grant (or revoke) a comp — free Pro access — for a user by email (D075).

The marketing lever: give press/VIPs full Pro without payment. A comp is just a
`subscriptions` row with source='comp', tier='pro', status='active' and no Lemon
Squeezy IDs, so `resolve_tier` treats it exactly like a paying subscriber. The Lemon
Squeezy webhook never touches comp rows (it writes source='lemonsqueezy').

The user must have **signed up (free) first** — a subscription row references
auth.users. Send them a signup link, then run this.

Usage:
    python scripts/grant_comp.py --email someone@example.com
    python scripts/grant_comp.py --email someone@example.com --until 2026-12-31
    python scripts/grant_comp.py --email someone@example.com --revoke

Requires DATABASE_URL with access to the auth schema (the cloud session pooler role).
Operator-run against the live DB.
"""
import argparse
import asyncio
import sys
from datetime import UTC, datetime

sys.path.insert(0, "engine")

from engine.db import create_pool


async def main(email: str, until: str | None, revoke: bool) -> None:
    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT id FROM auth.users WHERE email = $1", email)
            if user is None:
                print(f"No user with email '{email}'. They must sign up (free) first.")
                return
            user_id = user["id"]

            if revoke:
                result = await conn.execute(
                    "UPDATE subscriptions SET status = 'cancelled', updated_at = now() "
                    "WHERE user_id = $1 AND source = 'comp'",
                    user_id,
                )
                print(f"Revoked comp for {email} ({result}).")
                return

            period_end = None
            if until:
                period_end = datetime.fromisoformat(until).replace(tzinfo=UTC)

            await conn.execute(
                """
                INSERT INTO subscriptions (
                    user_id, tier, status, current_period_end, source, updated_at
                ) VALUES ($1, 'pro', 'active', $2, 'comp', now())
                ON CONFLICT (user_id) DO UPDATE SET
                    tier = 'pro',
                    status = 'active',
                    current_period_end = EXCLUDED.current_period_end,
                    source = 'comp',
                    cancelled_at = NULL,
                    updated_at = now()
                """,
                user_id, period_end,
            )
            window = f" until {until}" if until else " (no expiry)"
            print(f"Granted comp Pro to {email}{window}.")
    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grant/revoke comp Pro access by email.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--until", help="ISO date the comp expires, e.g. 2026-12-31")
    parser.add_argument("--revoke", action="store_true", help="Revoke an existing comp")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.until, args.revoke))
