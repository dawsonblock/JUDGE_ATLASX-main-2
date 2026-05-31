import { NextRequest, NextResponse } from "next/server";

const BACKEND =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const refreshToken = req.cookies.get("jta_refresh_token")?.value;

  if (!refreshToken) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const upstream = await fetch(`${BACKEND}/api/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${refreshToken}`,
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!upstream.ok) {
    // Refresh failed — clear cookies and signal the client to re-login.
    const response = NextResponse.json(
      { error: "Session expired" },
      { status: 401 },
    );
    response.cookies.set("jta_access_token", "", {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      maxAge: 0,
      path: "/",
    });
    response.cookies.set("jta_refresh_token", "", {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      maxAge: 0,
      path: "/api/auth/refresh",
    });
    return response;
  }

  const data = (await upstream.json()) as {
    access_token: string;
    refresh_token: string;
    token_type: string;
  };

  const response = NextResponse.json({ ok: true });
  response.cookies.set("jta_access_token", data.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 15, // 15 minutes
    path: "/",
  });
  response.cookies.set("jta_refresh_token", data.refresh_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 60 * 24 * 7, // 7 days
    path: "/api/auth/refresh",
  });
  return response;
}
