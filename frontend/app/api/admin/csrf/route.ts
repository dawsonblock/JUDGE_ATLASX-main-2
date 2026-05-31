import { NextResponse } from "next/server";
import {
  ADMIN_CSRF_COOKIE_NAME,
  issueAdminCsrfToken,
} from "../_auth";

export async function GET() {
  const token = issueAdminCsrfToken();
  const response = NextResponse.json({ csrf_token: token });
  response.cookies.set({
    name: ADMIN_CSRF_COOKIE_NAME,
    value: token,
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
  });
  return response;
}
