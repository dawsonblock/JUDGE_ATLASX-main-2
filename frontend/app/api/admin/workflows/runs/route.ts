import { NextRequest, NextResponse } from "next/server";
import { buildAdminAuthHeaders } from "../../_auth";

const backendBase =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function GET(req: NextRequest) {
  const { headers, configured } = buildAdminAuthHeaders(req);
  if (!configured) {
    return NextResponse.json(
      { error: "Admin auth not configured (Bearer JWT or server admin token required)" },
      { status: 503 },
    );
  }

  const capability = await fetch(`${backendBase}/api/admin/capabilities`, {
    method: "GET",
    headers,
    cache: "no-store",
  });
  const capabilityBody = await capability.json().catch(() => ({}));
  if (!capability.ok || capabilityBody.workflow_admin !== true) {
    return NextResponse.json(
      {
        error: "Workflow admin disabled",
        workflow_admin: false,
      },
      { status: 404 },
    );
  }

  const searchParams = req.nextUrl.searchParams.toString();
  const url = `${backendBase}/api/admin/workflows/runs${searchParams ? `?${searchParams}` : ""}`;
  const upstream = await fetch(url, {
    method: "GET",
    headers,
    cache: "no-store",
  });

  const body = await upstream.json().catch(() => ({}));
  return NextResponse.json(body, { status: upstream.status });
}
