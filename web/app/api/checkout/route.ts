import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

// Generates a Lemon Squeezy hosted-checkout URL for the selected variant (D050),
// embedding the user_id in custom_data. Degrades gracefully when Lemon Squeezy
// is not yet configured (D045) — no crash, explicit message.
export async function POST(request: Request) {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Please sign in to start a trial." }, { status: 401 });
  }

  const apiKey = process.env.LEMONSQUEEZY_API_KEY;
  const storeId = process.env.LEMONSQUEEZY_STORE_ID;
  const { variant } = (await request.json().catch(() => ({}))) as { variant?: string };
  const variantId =
    variant === "annual"
      ? process.env.LEMONSQUEEZY_VARIANT_ANNUAL
      : process.env.LEMONSQUEEZY_VARIANT_MONTHLY;

  if (!apiKey || !storeId || !variantId) {
    return NextResponse.json(
      { error: "Payments are not yet configured. Check back soon." },
      { status: 503 },
    );
  }

  const origin = new URL(request.url).origin;
  const res = await fetch("https://api.lemonsqueezy.com/v1/checkouts", {
    method: "POST",
    headers: {
      Accept: "application/vnd.api+json",
      "Content-Type": "application/vnd.api+json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      data: {
        type: "checkouts",
        attributes: {
          checkout_data: {
            email: user.email,
            custom: { user_id: user.id },
          },
          product_options: { redirect_url: `${origin}/subscribe/success` },
        },
        relationships: {
          store: { data: { type: "stores", id: storeId } },
          variant: { data: { type: "variants", id: variantId } },
        },
      },
    }),
  });

  if (!res.ok) {
    return NextResponse.json({ error: "Could not start checkout." }, { status: 502 });
  }

  const body = await res.json();
  const url = body?.data?.attributes?.url;
  if (!url) {
    return NextResponse.json({ error: "Could not start checkout." }, { status: 502 });
  }
  return NextResponse.json({ url });
}
