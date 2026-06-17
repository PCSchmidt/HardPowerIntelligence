// True when Lemon Squeezy checkout is fully configured (D045/D088). Reads server-only
// secret env, so call it only from Server Components / route handlers; in a client context
// those vars are undefined and this returns false — a safe "Pro not available yet" default.
// Marketing surfaces use this to degrade to "Pro coming soon" while payments are dark and
// switch back on automatically once the env is set — no separate client flag to maintain.
export function paymentsConfigured(): boolean {
  return Boolean(
    process.env.LEMONSQUEEZY_API_KEY &&
      process.env.LEMONSQUEEZY_STORE_ID &&
      (process.env.LEMONSQUEEZY_VARIANT_MONTHLY || process.env.LEMONSQUEEZY_VARIANT_ANNUAL),
  );
}
