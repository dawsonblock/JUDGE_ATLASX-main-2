import { NextRequest, NextResponse } from "next/server";
import { buildAdminAuthHeaders, hasValidAdminCsrf } from "../../../../_auth";

const backendBase =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

function contradictionPayload(body: Record<string, unknown>) {
  const decision = String(body.decision ?? body.action ?? "resolved");
  return {
    status: "resolved",
    resolution_note: `Resolution decision: ${decision}`,
  };
}

export async function POST(
  req: NextRequest,
  { params }: { params: { entityType: string; entityId: string } },
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

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const kind = params.entityType;

  if (kind === "contradictions") {
    const upstream = await fetch(
      `${backendBase}/api/admin/contradictions/${params.entityId}/resolve`,
      {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(contradictionPayload(body)),
        cache: "no-store",
      },
    );
    const payload = await upstream.json().catch(() => ({}));
    return NextResponse.json(payload, { status: upstream.status });
  }

  if (kind === "claims") {
    const decision = String(body.decision ?? body.action ?? "").toLowerCase();
    if (decision === "rejected") {
      const upstream = await fetch(
        `${backendBase}/api/admin/memory/claims/${params.entityId}/invalidate`,
        {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify({ reason: "manual_reject" }),
          cache: "no-store",
        },
      );
      const payload = await upstream.json().catch(() => ({}));
      return NextResponse.json(payload, { status: upstream.status });
    }

    return NextResponse.json(
      { error: "Approve action is not implemented for memory claims in current backend." },
      { status: 501 },
    );
  }

  if (kind === "entities") {
    const entityType = String(body.entity_type ?? "source");
    const upstream = await fetch(
      `${backendBase}/api/admin/review-queue/${entityType}/${params.entityId}/decision`,
      {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
      },
    );
    const payload = await upstream.json().catch(() => ({}));
    return NextResponse.json(payload, { status: upstream.status });
  }

  const upstream = await fetch(
    `${backendBase}/api/admin/review-queue/${kind}/${params.entityId}/decision`,
    {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    },
  );
  const payload = await upstream.json().catch(() => ({}));
  return NextResponse.json(payload, { status: upstream.status });
}
