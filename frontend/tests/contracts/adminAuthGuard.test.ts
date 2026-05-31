import { describe, expect, it, vi } from "vitest";

import { resolveAdminAccess } from "@/app/admin/authGuard";

describe("admin auth guard", () => {
  it("denies access when token is missing", async () => {
    const result = await resolveAdminAccess(undefined);

    expect(result.allowed).toBe(false);
    expect(result.reason).toBe("missing_token");
  });

  it("denies access when /api/auth/me returns unauthorized", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("unauthorized", { status: 401 }));

    const result = await resolveAdminAccess("stale-token", fetchImpl);

    expect(result.allowed).toBe(false);
    expect(result.reason).toBe("auth_me_401");
  });

  it("denies access for non-admin role", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          email: "viewer@example.com",
          role: "viewer",
          display_name: "Viewer",
          is_active: true,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    const result = await resolveAdminAccess("valid-viewer-token", fetchImpl);

    expect(result.allowed).toBe(false);
    expect(result.reason).toBe("insufficient_role");
    expect(result.role).toBe("viewer");
  });

  it("allows access for source_admin role", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          email: "source-admin@example.com",
          role: "source_admin",
          display_name: "Source Admin",
          is_active: true,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    const result = await resolveAdminAccess("valid-admin-token", fetchImpl);

    expect(result.allowed).toBe(true);
    expect(result.reason).toBe("ok");
    expect(result.role).toBe("source_admin");
  });
});
