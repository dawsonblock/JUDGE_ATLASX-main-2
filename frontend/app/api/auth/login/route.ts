import { NextRequest, NextResponse } from "next/server";

const BACKEND =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const upstream = await fetch(`${BACKEND}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!upstream.ok) {
    const detail = await upstream.json().catch(() => ({ detail: "Login failed" }));
    return NextResponse.json(detail, { status: upstream.status });
  }

  const data = (await upstream.json()) as {
    access_token: string;
    refresh_token: string;
    token_type: string;
  };

  const response = NextResponse.json({ ok: true });

  // Short-lived access token — 15 minutes
  response.cookies.set("jta_access_token", data.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 15,
    path: "/",
  });

  // Long-lived refresh token — 7 days
  response.cookies.set("jta_refresh_token", data.refresh_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 60 * 24 * 7,
    path: "/api/auth/refresh",
  });

  return response;
}
