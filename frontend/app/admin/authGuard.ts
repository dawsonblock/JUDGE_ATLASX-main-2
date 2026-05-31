export type AuthMeResponse = {
  email: string;
  role: string;
  display_name: string | null;
  is_active: boolean;
};

const ADMIN_ROLES = new Set(["admin", "owner", "source_admin"]);

function apiBase(): string {
  return (
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000"
  );
}

export function isAdminRole(role: string | null | undefined): boolean {
  if (!role) {
    return false;
  }
  return ADMIN_ROLES.has(role);
}

export async function resolveAdminAccess(
  accessToken: string | undefined,
  fetchImpl: typeof fetch = fetch,
): Promise<{ allowed: boolean; reason: string; role: string | null }> {
  if (!accessToken) {
    return { allowed: false, reason: "missing_token", role: null };
  }

  try {
    const response = await fetchImpl(`${apiBase()}/api/auth/me`, {
      method: "GET",
      headers: {
        authorization: `Bearer ${accessToken}`,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return {
        allowed: false,
        reason: `auth_me_${response.status}`,
        role: null,
      };
    }

    const profile = (await response.json()) as AuthMeResponse;
    if (!isAdminRole(profile.role)) {
      return {
        allowed: false,
        reason: "insufficient_role",
        role: profile.role,
      };
    }

    return { allowed: true, reason: "ok", role: profile.role };
  } catch {
    return { allowed: false, reason: "auth_me_error", role: null };
  }
}
