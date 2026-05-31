import { NextRequest, NextResponse } from "next/server";
import { buildAdminAuthHeaders } from "../_auth";

const backendBase =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

/**
 * GET /api/admin/ingestion-runs
 *
 * Proxies to the backend GET /api/admin/ingestion-runs
 * with server-side admin auth injection.
 * Forwards all query parameters (source_key, status, limit, skip).
 */
export async function GET(req: NextRequest) {
  const { headers, configured } = buildAdminAuthHeaders(req);
  if (!configured) {
    return NextResponse.json(
      { error: "Admin auth not configured (Bearer JWT or server admin token required)" },
      { status: 503 },
    );
  }

  // Forward query parameters
  const searchParams = req.nextUrl.searchParams.toString();
  const url = `${backendBase}/api/admin/ingestion-runs${searchParams ? `?${searchParams}` : ""}`;

  const upstream = await fetch(url, {
    method: "GET",
    headers,
    cache: "no-store",
  });

  const body = await upstream.json().catch(() => ({}));
  return NextResponse.json(body, { status: upstream.status });
}
