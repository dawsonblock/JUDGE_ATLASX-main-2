import { NextRequest, NextResponse } from "next/server";

const BACKEND =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const refreshToken = req.cookies.get("jta_refresh_token")?.value;

  if (refreshToken) {
    // Best-effort: tell the backend to revoke this session.
    await fetch(`${BACKEND}/api/auth/logout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    }).catch(() => {
      // Ignore upstream errors — we clear cookies regardless.
    });
  }

  const response = NextResponse.json({ ok: true });
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
