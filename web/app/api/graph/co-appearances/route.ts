import { NextResponse } from "next/server";

import { getEdgeCoappearances } from "@/lib/api/graph";

// Client-side (the graph is an interactive client component) proxy to the FastAPI edge-evidence
// endpoint. apiFetch is server-only and attaches the caller's Supabase session, so it must be called
// from a route handler, not the browser. Reads a,b (entity ids) from the query.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const a = searchParams.get("a");
  const b = searchParams.get("b");
  if (!a || !b) {
    return NextResponse.json({ error: "a and b are required" }, { status: 400 });
  }
  const { data, status } = await getEdgeCoappearances(a, b);
  if (!data) {
    return NextResponse.json({ error: "unavailable" }, { status: status || 502 });
  }
  return NextResponse.json(data);
}
