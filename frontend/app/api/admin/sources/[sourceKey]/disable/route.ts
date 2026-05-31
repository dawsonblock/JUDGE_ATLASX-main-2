import { NextRequest, NextResponse } from "next/server";
import { buildAdminAuthHeaders, hasValidAdminCsrf } from "../../../_auth";

const backendBase =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(
  req: NextRequest,
  { params }: { params: { sourceKey: string } },
) {
  if (!hasValidAdminCsrf(req)) {
    return NextResponse.json(
      { error: "CSRF validation failed for admin mutation" },
      { status: 403 },
    );
  }

  const { headers, configured } = buildAdminAuthHeaders(req);
  if (!configured) {
    return NextResponse.json(
      { error: "Admin auth not configured (Bearer JWT or server admin token required)" },
      { status: 503 },
    );
  }
  const upstream = await fetch(
    `${backendBase}/api/admin/sources/${params.sourceKey}/disable`,
    {
      method: "POST",
      headers,
      cache: "no-store",
    },
  );
  const body = await upstream.json();
  return NextResponse.json(body, { status: upstream.status });
}
