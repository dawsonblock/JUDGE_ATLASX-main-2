export const ADMIN_CSRF_COOKIE_NAME = "jta_admin_csrf";
export const ADMIN_CSRF_HEADER_NAME = "x-jta-csrf-token";

function readCookie(req: Request, name: string): string | null {
  const cookieHeader = req.headers.get("cookie") ?? "";
  const pattern = new RegExp(`(?:^|;\\s*)${name}=([^;]+)`);
  const match = cookieHeader.match(pattern);
  return match?.[1] ?? null;
}

export function buildAdminAuthHeaders(req: Request): {
  headers: HeadersInit;
  configured: boolean;
} {
  // 1. JWT cookie — preferred; set by /api/auth/login route handler.
  const cookieToken = readCookie(req, "jta_access_token");
  if (cookieToken) {
    return {
      headers: { authorization: `Bearer ${cookieToken}` },
      configured: true,
    };
  }

  // 2. Explicit Bearer header (e.g. forwarded by a server component).
  const authHeader = req.headers.get("authorization");
  const hasBearer = Boolean(authHeader?.startsWith("Bearer "));
  if (hasBearer && authHeader) {
    return {
      headers: { authorization: authHeader },
      configured: true,
    };
  }

  const legacyEnabled =
    (process.env.JTA_ENABLE_LEGACY_ADMIN_TOKEN || "").toLowerCase() === "true";
  const token = process.env.JTA_ADMIN_TOKEN;
  if (legacyEnabled && token) {
    return {
      headers: { "x-jta-admin-token": token },
      configured: true,
    };
  }

  return { headers: {}, configured: false };
}

export function issueAdminCsrfToken(): string {
  // UUID without separators keeps header/cookie payload compact.
  return crypto.randomUUID().replace(/-/g, "");
}

export function hasValidAdminCsrf(req: Request): boolean {
  const headerToken = req.headers.get(ADMIN_CSRF_HEADER_NAME);
  const cookieToken = readCookie(req, ADMIN_CSRF_COOKIE_NAME);
  if (!headerToken || !cookieToken) {
    return false;
  }
  if (headerToken.length < 16 || cookieToken.length < 16) {
    return false;
  }
  return headerToken === cookieToken;
}
