import { NextRequest, NextResponse } from "next/server";
import { buildAdminAuthHeaders, hasValidAdminCsrf } from "../../../_auth";

const backendBase =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

/**
 * POST /api/admin/ingestion-runs/[runId]/retry
 *
 * Proxies to the backend POST /api/admin/ingestion-runs/{run_id}/retry
 * with server-side admin auth injection.
 */
export async function POST(
  req: NextRequest,
  { params }: { params: { runId: string } },
) {
  if (!hasValidAdminCsrf(req)) {
    return NextResponse.json(
      { error: "CSRF validation failed for admin mutation" },
      { status: 403 },
    );
  }

  const { headers: authHeaders, configured } = buildAdminAuthHeaders(req);
  if (!configured) {
    return NextResponse.json(
      { error: "Admin auth not configured (Bearer JWT or server admin token required)" },
      { status: 503 },
    );
  }

  const upstream = await fetch(
    `${backendBase}/api/admin/ingestion-runs/${params.runId}/retry`,
    {
      method: "POST",
      headers: authHeaders,
      cache: "no-store",
    },
  );

  const body = await upstream.json().catch(() => ({}));
  return NextResponse.json(body, { status: upstream.status });
}
