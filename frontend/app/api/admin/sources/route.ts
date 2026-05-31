import { NextResponse } from "next/server";
import { buildAdminAuthHeaders } from "../_auth";

const backendBase =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function GET(req: Request) {
  const { headers, configured } = buildAdminAuthHeaders(req);
  if (!configured) {
    return NextResponse.json(
      { error: "Admin auth not configured (Bearer JWT or server admin token required)" },
      { status: 503 },
    );
  }
  const url = new URL(req.url);
  const query = url.search ? url.search : "";
  const upstream = await fetch(`${backendBase}/api/admin/sources${query}`, {
    headers,
    cache: "no-store",
  });
  const body = await upstream.json();
  return NextResponse.json(body, { status: upstream.status });
}
